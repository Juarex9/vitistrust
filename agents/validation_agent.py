# agents/validation_agent.py
import json
import logging
from pathlib import Path
from typing import Any
from web3 import Web3

from backend.benchmarks import compute_regional_benchmark

logger = logging.getLogger("vitistrust.validation")

# Cargar regiones vinícolas desde GeoJSON
WINE_REGIONS_GEOJSON = None
REGIONS_FILE = Path("backend/data/wine_regions.json")

def _load_wine_regions() -> dict:
    """Carga regiones desde archivo GeoJSON."""
    global WINE_REGIONS_GEOJSON
    if WINE_REGIONS_GEOJSON is None:
        if REGIONS_FILE.exists():
            WINE_REGIONS_GEOJSON = json.loads(REGIONS_FILE.read_text(encoding="utf-8"))
        else:
            WINE_REGIONS_GEOJSON = {"features": []}
    return WINE_REGIONS_GEOJSON

def _point_in_polygon(lat: float, lon: float, polygon: list) -> bool:
    """Ray casting algorithm para verificar si punto está dentro del polígono."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def validate_geolocation_polygon(lat: float, lon: float) -> dict[str, Any]:
    """
    Valida coordenadas contra polígonos GeoJSON reales.
    
    Args:
        lat: Latitud
        lon: Longitud
        
    Returns:
        Dict con validación, región y metadata
    """
    geojson = _load_wine_regions()
    
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        
        if geometry.get("type") != "Polygon":
            continue
            
        coords = geometry.get("coordinates", [[]])[0]  # Primer ring
        if _point_in_polygon(lat, lon, coords):
            return {
                "valid": True,
                "region": props.get("name"),
                "region_key": props.get("region_key"),
                "province": props.get("province"),
                "avg_ndvi": props.get("avg_ndvi"),
                "wine_type": props.get("type"),
                "method": "polygon",
                "message": f"Coordinates within {props.get('name')}, {props.get('province')}"
            }
    
    # Fallback a bounding box
    return validate_geolocation(lat, lon)
WINE_REGIONS = {
    "VALLE_DE_UCO": {
        "name": "Valle de Uco",
        "lat_min": -34.0,
        "lat_max": -33.2,
        "lon_min": -69.5,
        "lon_max": -68.9
    },
    "LUJAN_DE_CUYO": {
        "name": "Luján de Cuyo",
        "lat_min": -33.2,
        "lat_max": -32.9,
        "lon_min": -69.1,
        "lon_max": -68.7
    },
    "MAIPU": {
        "name": "Maipú",
        "lat_min": -33.1,
        "lat_max": -32.85,
        "lon_min": -68.9,
        "lon_max": -68.65
    },
    "EAST_MENDOZA": {
        "name": "Este de Mendoza",
        "lat_min": -33.0,
        "lat_max": -32.7,
        "lon_min": -68.7,
        "lon_max": -68.3
    },
    "SAN_RAFAEL": {
        "name": "San Rafael",
        "lat_min": -34.8,
        "lat_max": -34.3,
        "lon_min": -68.5,
        "lon_max": -67.9
    }
}

# Minimum NDVI for vegetation detection
MIN_VEGETATION_NDVI = 0.3

# ERC-721 Interface ID
ERC721_INTERFACE_ID = "0x80ac58cd"


def validate_geolocation(lat: float, lon: float) -> dict[str, Any]:
    """
    Validate that coordinates are within known wine regions.
    Primero intenta polígonos GeoJSON, luego fallback a bounding boxes.
    
    Args:
        lat: Latitud
        lon: Longitud
        
    Returns:
        Dict con status, region_name, y metadata
    """
    # Primero intentar con polígonos
    result = validate_geolocation_polygon(lat, lon)
    if result.get("valid"):
        return result
    
    # Fallback a bounding boxes para backwards compatibility
    for region_key, region in WINE_REGIONS.items():
        if (region["lat_min"] <= lat <= region["lat_max"] and 
            region["lon_min"] <= lon <= region["lon_max"]):
            return {
                "valid": True,
                "region": region["name"],
                "region_key": region_key,
                "method": "bounding_box",
                "message": f"Coordinates within {region['name']}"
            }
    
    # Calculate distance to nearest region center
    nearest_region = _find_nearest_region(lat, lon)
    return {
        "valid": False,
        "region": None,
        "region_key": None,
        "nearest_region": nearest_region["name"],
        "distance_km": nearest_region["distance"],
        "message": f"Coordinates not in wine region. Nearest: {nearest_region['name']} ({nearest_region['distance']:.1f}km)"
    }


def _find_nearest_region(lat: float, lon: float) -> dict[str, Any]:
    """Find the nearest wine region to given coordinates."""
    region_centers = {
        "VALLE_DE_UCO": (-33.6, -69.2),
        "LUJAN_DE_CUYO": (-33.05, -68.9),
        "MAIPU": (-32.97, -68.77),
        "EAST_MENDOZA": (-32.85, -68.5),
        "SAN_RAFAEL": (-34.55, -68.2)
    }
    
    import math
    
    min_distance = float('inf')
    nearest = None
    
    for name, (center_lat, center_lon) in region_centers.items():
        # Simple Euclidean distance approximation
        distance = math.sqrt((lat - center_lat)**2 + (lon - center_lon)**2) * 111  # km per degree
        if distance < min_distance:
            min_distance = distance
            nearest = {"name": name.replace("_", " "), "distance": distance}
    
    return nearest


def validate_vegetation(ndvi: float) -> dict[str, Any]:
    """
    Validate that NDVI indicates vegetation presence.
    
    Args:
        ndvi: NDVI value from satellite analysis
        
    Returns:
        Dict with status and message
    """
    if ndvi < 0:
        return {
            "valid": False,
            "message": "Invalid NDVI value (negative)"
        }
    
    if ndvi < MIN_VEGETATION_NDVI:
        return {
            "valid": False,
            "message": f"NDVI ({ndvi}) below vegetation threshold ({MIN_VEGETATION_NDVI}). Area may be bare soil or urban."
        }
    
    # Classify vegetation health
    health = "low"
    if ndvi >= 0.7:
        health = "high"
    elif ndvi >= 0.5:
        health = "moderate"
    
    return {
        "valid": True,
        "health": health,
        "message": f"Vegetation detected (NDVI: {ndvi}, health: {health})"
    }


def validate_erc721_contract(w3: Web3, contract_address: str) -> dict[str, Any]:
    """
    Validate that address is a valid ERC-721 contract.
    
    Args:
        w3: Web3 instance
        contract_address: Contract address to validate
        
    Returns:
        Dict with validation status and contract info
    """
    try:
        checksum_address = Web3.to_checksum_address(contract_address)
        
        # Check if address has code
        code = w3.eth.get_code(checksum_address)
        if not code:
            return {
                "valid": False,
                "message": "Address has no contract code"
            }
        
        # Try to get contract name (ERC-721 metadata)
        erc721_abi = [
            {
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "supportsInterface",
                "inputs": [{"name": "interfaceId", "type": "bytes4"}],
                "outputs": [{"name": "", "type": "bool"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        contract = w3.eth.contract(address=checksum_address, abi=erc721_abi)
        
        try:
            name = contract.functions.name().call()
        except:
            name = "Unknown"
        
        return {
            "valid": True,
            "is_contract": True,
            "name": name,
            "message": f"Valid contract: {name}"
        }
        
    except Exception as e:
        logger.error(f"ERC-721 validation error: {e}")
        return {
            "valid": False,
            "message": f"Contract validation failed: {str(e)}"
        }


def validate_token_exists(w3: Web3, contract_address: str, token_id: int) -> dict[str, Any]:
    """
    Validate that token ID exists in the contract.
    
    Args:
        w3: Web3 instance
        contract_address: Contract address
        token_id: Token ID to check
        
    Returns:
        Dict with validation status and token info
    """
    try:
        checksum_address = Web3.to_checksum_address(contract_address)
        
        # ERC-721 ownerOf function
        erc721_abi = [
            {
                "inputs": [{"name": "tokenId", "type": "uint256"}],
                "name": "ownerOf",
                "outputs": [{"name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        contract = w3.eth.contract(address=checksum_address, abi=erc721_abi)
        owner = contract.functions.ownerOf(token_id).call()
        
        return {
            "valid": True,
            "exists": True,
            "owner": owner,
            "message": f"Token #{token_id} exists, owned by {owner[:6]}...{owner[-4:]}"
        }
        
    except Exception as e:
        logger.warning(f"Token validation error: {e}")
        return {
            "valid": True,  # Don't fail the whole process for token check
            "exists": False,
            "message": f"Could not verify token existence: {str(e)}"
        }


def validate_certificate_not_exists(w3: Web3, contract_address: str, token_id: int, vitis_contract) -> dict[str, Any]:
    """
    Check if certificate already exists for this asset.
    
    Args:
        w3: Web3 instance
        contract_address: Asset contract address
        token_id: Token ID
        vitis_contract: VitisRegistry contract instance
        
    Returns:
        Dict with certificate status
    """
    try:
        if not vitis_contract:
            return {
                "exists": False,
                "message": "VitisRegistry not configured"
            }
        
        normalized_address = Web3.to_checksum_address(contract_address.lower())
        
        cert = vitis_contract.functions.certificates(
            normalized_address,
            token_id
        ).call()
        
        score = cert[0]
        timestamp = cert[1]
        topic_id = cert[2]
        
        if score > 0 and timestamp > 0:
            return {
                "exists": True,
                "score": score,
                "timestamp": timestamp,
                "topic_id": topic_id,
                "message": f"Certificate already exists (Score: {score}, Date: {timestamp})"
            }
        
        return {
            "exists": False,
            "message": "No existing certificate for this asset"
        }
        
    except Exception as e:
        logger.warning(f"Certificate check error: {e}")
        return {
            "exists": False,
            "message": "Could not verify certificate status"
        }


def validate_vineyard(
    lat: float,
    lon: float,
    ndvi: float,
    asset_address: str,
    token_id: int,
    w3: Web3,
    vitis_contract
) -> dict[str, Any]:
    """
    Run all validations for a vineyard.
    
    Args:
        lat: Latitude
        lon: Longitude
        ndvi: NDVI value
        asset_address: Contract address
        token_id: Token ID
        w3: Web3 instance
        vitis_contract: VitisRegistry contract
        
    Returns:
        Dict with all validation results
    """
    validations = {}
    
    # 1. Geolocation validation
    validations["geolocation"] = validate_geolocation(lat, lon)

    # 2. Vegetation validation
    validations["vegetation"] = validate_vegetation(ndvi)

    # 2b. Regional benchmark (reuse detected region)
    validations["regional_benchmark"] = compute_regional_benchmark(
        ndvi=ndvi,
        region_key=validations["geolocation"].get("region_key"),
        region_name=validations["geolocation"].get("region"),
    )
    
    # 3. ERC-721 contract validation
    validations["contract"] = validate_erc721_contract(w3, asset_address) if w3.is_address(asset_address) else {
        "valid": False,
        "message": "Invalid address format"
    }
    
    # 4. Token existence
    if validations["contract"]["valid"]:
        validations["token"] = validate_token_exists(w3, asset_address, token_id)
    else:
        validations["token"] = {"valid": False, "exists": False, "message": "Contract validation failed"}
    
    # 5. Certificate check
    validations["certificate"] = validate_certificate_not_exists(w3, asset_address, token_id, vitis_contract)
    
    # Overall result
    all_valid = (
        validations["geolocation"]["valid"] and
        validations["vegetation"]["valid"]
    )
    
    return {
        "all_valid": all_valid,
        "can_verify": all_valid,  # Allow verification if location and vegetation are valid
        "validations": validations
    }


if __name__ == "__main__":
    # Test validation
    print("Testing validation...")
    
    # Test geolocation (Valle de Uco)
    result = validate_geolocation(-33.4942, -69.2429)
    print(f"Geolocation: {result}")
    
    # Test vegetation (healthy vineyard)
    result = validate_vegetation(0.68)
    print(f"Vegetation: {result}")
    
    # Test vegetation (no vegetation)
    result = validate_vegetation(0.15)
    print(f"Vegetation (no veg): {result}")
