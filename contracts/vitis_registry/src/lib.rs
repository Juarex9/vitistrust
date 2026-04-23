// VitisRegistry: Smart Contract en Soroban para storing VitisScores
#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, symbol_short, Address, BytesN, Env, Map, String, Symbol, Vec,
};

/// Storage keys del contrato
#[derive(Clone)]
#[contracttype]
pub enum DataKey {
    Admin,
    Records,
    Locations,
}

/// Registro de ubicación de un viñedo (almacenado en primera certificación)
#[derive(Clone)]
#[contracttype]
pub struct VitisLocation {
    pub lat: i128,      // Latitud multiply by 10^6
    pub lon: i128,      // Longitud multiply by 10^6
    pub geohash: String,
}

/// Registro de VitisScore para un viñedo
#[derive(Clone)]
#[contracttype]
pub struct VitisRecord {
    pub score: u32,
    pub timestamp: u64,
    pub hedera_txn_id: BytesN<32>,
    pub evidence_cid: String,
    pub auditor: Address,
}

#[contract]
pub struct VitisRegistry;

#[contractimpl]
impl VitisRegistry {
    pub fn initialize(env: Env, admin: Address) {
        if env.storage().instance().get::<DataKey, Address>(&DataKey::Admin).is_some() {
            panic!("Contract already initialized");
        }
        
        env.storage().instance().set(&DataKey::Admin, &admin);
        
        // Historial de registros por farm_id (lista de auditorías)
        let empty_map: Map<String, Vec<VitisRecord>> = Map::new(&env);
        env.storage().instance().set(&DataKey::Records, &empty_map);
    }

    pub fn update_score(
        env: Env,
        farm_id: String,
        score: u32,
        hedera_txn_id: BytesN<32>,
        evidence_cid: String,
    ) {
        let admin: Address = env.storage().instance()
            .get(&DataKey::Admin)
            .expect("Contract not initialized");
        
        admin.require_auth();

        if score > 100 {
            panic!("Score must be 0-100");
        }

        // Obtener historial existente o crear nuevo
        let mut history: Vec<VitisRecord> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Vec::new(&env))
            .get(&farm_id)
            .unwrap_or_else(|| Vec::new(&env));

        let record = VitisRecord {
            score,
            timestamp: env.ledger().timestamp(),
            hedera_txn_id,
            evidence_cid,
            auditor: admin.clone(),
        };

        // Agregar al historial (append)
        history.push_back(record);
        
        // Guardar en mapa de историал
        let mut all_records: Map<String, Vec<VitisRecord>> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));
        
        all_records.set(farm_id.clone(), history);
        env.storage().instance().set(&DataKey::Records, &all_records);

        // === ARREGLO DEL EVENTO ===
        // Usamos Symbol::new porque el nombre es largo (> 9 chars)
        env.events().publish(
            (Symbol::new(&env, "score_updated"), farm_id.clone()), // Tópicos en una tupla
            score, // Enviamos el score como dato del evento
        );
    }

    pub fn get_score(env: Env, farm_id: String) -> (u32, u64, BytesN<32>, String, Address) {
        let all_records: Map<String, Vec<VitisRecord>> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));

        let history = all_records.get(&farm_id).unwrap_or_else(|| {
            panic!("No record found for farm");
        });

        // Obtener el último registro (más reciente)
        let latest = history.get(history.len().saturating_sub(1)).unwrap_or_else(|| {
            panic!("Empty history");
        });

        (
            latest.score,
            latest.timestamp,
            latest.hedera_txn_id,
            latest.evidence_cid,
            latest.auditor,
        )
    }

    /// Obtener historial completo de auditorías
    pub fn get_history(env: Env, farm_id: String) -> Vec<VitisRecord> {
        let all_records: Map<String, Vec<VitisRecord>> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));

        all_records.get(&farm_id).unwrap_or_else(|| Vec::new(&env))
    }

    /// Obtener auditoría por índice
    pub fn get_record_at(env: Env, farm_id: String, index: u32) -> (u32, u64, BytesN<32>, String, Address) {
        let all_records: Map<String, Vec<VitisRecord>> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));

        let history = all_records.get(&farm_id).unwrap_or_else(|| Vec::new(&env));
        
        let record = history.get(index).unwrap_or_else(|| {
            panic!("Index out of bounds");
        });

        (
            record.score,
            record.timestamp,
            record.hedera_txn_id,
            record.evidence_cid,
            record.auditor,
        )
    }

    pub fn has_record(env: Env, farm_id: String) -> bool {
        let all_records: Map<String, Vec<VitisRecord>> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));

        let history = all_records.get(&farm_id).unwrap_or_else(|| Vec::new(&env));
        history.len() > 0
    }

    pub fn set_admin(env: Env, new_admin: Address) {
        let admin: Address = env.storage().instance()
            .get(&DataKey::Admin)
            .expect("Contract not initialized");
        
        admin.require_auth();
        env.storage().instance().set(&DataKey::Admin, &new_admin);
    }

    pub fn set_location(
        env: Env,
        farm_id: String,
        lat: i128,
        lon: i128,
        geohash: String,
    ) {
        let admin: Address = env.storage().instance()
            .get(&DataKey::Admin)
            .expect("Contract not initialized");
        
        admin.require_auth();

        // Validación básica de coordenadas
        if lat.abs() > 90000000 || lon.abs() > 180000000 {
            panic!("Invalid coordinates range");
        }

        let mut locations: Map<String, VitisLocation> = env.storage()
            .instance()
            .get(&DataKey::Locations)
            .unwrap_or_else(|| Map::new(&env));

        let location = VitisLocation {
            lat,
            lon,
            geohash,
        };

        locations.set(farm_id.clone(), location);
        env.storage().instance().set(&DataKey::Locations, &locations);

        env.events().publish(
            (Symbol::new(&env, "location_set"), farm_id.clone()),
            lat,
        );
    }

    pub fn get_location(env: Env, farm_id: String) -> (i128, i128, String) {
        let locations: Map<String, VitisLocation> = env.storage()
            .instance()
            .get(&DataKey::Locations)
            .unwrap_or_else(|| Map::new(&env));

        let location = locations.get(farm_id).unwrap_or_else(|| {
            panic!("No location found for farm");
        });

        (location.lat, location.lon, location.geohash)
    }

    pub fn has_location(env: Env, farm_id: String) -> bool {
        let locations: Map<String, VitisLocation> = env.storage()
            .instance()
            .get(&DataKey::Locations)
            .unwrap_or_else(|| Map::new(&env));

        locations.contains_key(farm_id)
    }
}