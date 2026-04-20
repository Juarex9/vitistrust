// VitisRegistry: Smart Contract en Soroban para storing VitisScores
// 
// Este contrato almacena los VitisScores de viñedos tokenizados.
// Solo el oráculo (admin) puede actualizar los scores.
// Cada actualización queda registrada con timestamp y tx de Hedera.

#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype, Address, BytesN, Env, Map, String,
};

/// Storage keys del contrato
#[derive(Clone)]
#[contracttype]
pub enum DataKey {
    /// Admin - la dirección del oráculo autorizada
    Admin,
    /// Records - Mapa de farm_id -> VitisRecord
    Records,
}

/// Registro de VitisScore para un viñedo
#[derive(Clone)]
#[contracttype]
pub struct VitisRecord {
    pub score: u32,              // VitisScore (0-100)
    pub timestamp: u64,           // Unix timestamp
    pub hedera_txn_id: BytesN<32>, // Tx ID de Hedera (32 bytes)
    pub evidence_cid: String,     // CID del paquete de evidencia en IPFS/Filecoin
    pub auditor: Address,        // Dirección que actualizó
}

/// Evento cuando se actualiza un score
#[contract]
pub struct VitisRegistry;

#[contractimpl]
impl VitisRegistry {
    /// Inicializa el contrato con la dirección del admin (oráculo)
    pub fn initialize(env: Env, admin: Address) {
        // Solo inicializar una vez
        if env.storage().instance().get::<DataKey, Address>(&DataKey::Admin).is_some() {
            panic!("Contract already initialized");
        }
        
        // Guardar admin
        env.storage().instance().set(&DataKey::Admin, &admin);
        
        // Inicializar mapa de registros vacío
        let empty_map: Map<String, VitisRecord> = Map::new(&env);
        env.storage().instance().set(&DataKey::Records, &empty_map);
    }

    /// Actualiza el VitisScore de un viñedo (solo admin)
    /// 
    /// # Arguments
    /// * `farm_id` - Identificador del viñedo (string limitado a 10 chars)
    /// * `score` - VitisScore (0-100)
    /// * `hedera_txn_id` - Transaction ID de Hedera HCS (32 bytes)
    pub fn update_score(
        env: Env,
        farm_id: String,
        score: u32,
        hedera_txn_id: BytesN<32>,
        evidence_cid: String,
    ) {
        // === AUTORIZACIÓN: Solo el admin puede actualizar ===
        let admin: Address = env.storage().instance()
            .get(&DataKey::Admin)
            .expect("Contract not initialized");
        
        // require_auth() verifica que el caller es el admin
        admin.require_auth();

        // Validar score
        if score > 100 {
            panic!("Score must be 0-100");
        }

        // Obtener registros existentes
        let mut records: Map<String, VitisRecord> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));

        // Crear nuevo registro
        let record = VitisRecord {
            score,
            timestamp: env.ledger().timestamp(),
            hedera_txn_id,
            evidence_cid,
            auditor: admin.clone(),
        };

        // Guardar
        records.set(farm_id.clone(), record);
        env.storage().instance().set(&DataKey::Records, &records);

        // Emitir evento
        env.events().publish(
            &(String::from_str(&env, "score_updated")),
            &farm_id,
        );
    }

    /// Consulta el VitisScore de un viñedo
    pub fn get_score(env: Env, farm_id: String) -> (u32, u64, BytesN<32>, String, Address) {
        let records: Map<String, VitisRecord> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));

        let record = records.get(farm_id).unwrap_or_else(|| {
            panic!("No record found for farm");
        });

        (
            record.score,
            record.timestamp,
            record.hedera_txn_id,
            record.evidence_cid,
            record.auditor,
        )
    }

    /// Verifica si existe un registro
    pub fn has_record(env: Env, farm_id: String) -> bool {
        let records: Map<String, VitisRecord> = env.storage()
            .instance()
            .get(&DataKey::Records)
            .unwrap_or_else(|| Map::new(&env));

        records.contains_key(farm_id)
    }

    /// Transfiere admin a nueva dirección
    pub fn set_admin(env: Env, new_admin: Address) {
        let admin: Address = env.storage().instance()
            .get(&DataKey::Admin)
            .expect("Contract not initialized");
        
        admin.require_auth();
        env.storage().instance().set(&DataKey::Admin, &new_admin);
    }
}
