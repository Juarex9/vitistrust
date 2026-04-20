#![cfg(test)]

mod test {
    use soroban_sdk::{testutils::Address as _, Address, BytesN, Env, String};

    use crate::{VitisRegistry, VitisRegistryClient};

    // Generar 32 bytes para hedera_txn_id
    fn generate_tx_id() -> BytesN<32> {
        let mut arr = [0u8; 32];
        arr[0] = 0x01;
        arr[31] = 0xFF;
        BytesN::from_array(&Env::default(), &arr)
    }

    #[test]
    fn test_initialize() {
        let env = Env::default();
        env.mock_all_auths();
        
        let contract_id = env.register(VitisRegistry, ());
        let client = VitisRegistryClient::new(&env, &contract_id);
        
        let admin = Address::generate(&env);
        
        client.initialize(&admin);
        
        // Verificar que el admin fue configurado
        let has_record = client.has_record(&String::from_str(&env, "test_farm"));
        assert!(!has_record); // No hay registros aún
    }

    #[test]
    fn test_update_and_get_score() {
        let env = Env::default();
        env.mock_all_auths();
        
        let contract_id = env.register(VitisRegistry, ());
        let client = VitisRegistryClient::new(&env, &contract_id);
        
        let admin = Address::generate(&env);
        client.initialize(&admin);
        
        // Actualizar score
        let farm_id = String::from_str(&env, "mendoza_1");
        let tx_id = generate_tx_id();
        let evidence_cid = String::from_str(&env, "bafybeigdyrzt5...");

        client.update_score(&farm_id, &85, &tx_id, &evidence_cid);
        
        // Verificar
        let (score, timestamp, _tx_id, stored_cid, auditor) = client.get_score(&farm_id);
        
        assert_eq!(score, 85);
        assert!(timestamp > 0);
        assert_eq!(stored_cid, evidence_cid);
        assert_eq!(auditor, admin);
    }

    #[test]
    #[should_panic(expected = "Contract already initialized")]
    fn test_double_initialize() {
        let env = Env::default();
        env.mock_all_auths();
        
        let contract_id = env.register(VitisRegistry, ());
        let client = VitisRegistryClient::new(&env, &contract_id);
        
        let admin1 = Address::generate(&env);
        let admin2 = Address::generate(&env);
        
        client.initialize(&admin1);
        client.initialize(&admin2); // Esto debe panic
    }

    #[test]
    #[should_panic(expected = "Score must be 0-100")]
    fn test_invalid_score() {
        let env = Env::default();
        env.mock_all_auths();
        
        let contract_id = env.register(VitisRegistry, ());
        let client = VitisRegistryClient::new(&env, &contract_id);
        
        let admin = Address::generate(&env);
        client.initialize(&admin);
        
        let farm_id = String::from_str(&env, "test");
        let tx_id = generate_tx_id();
        let evidence_cid = String::from_str(&env, "bafybeigdyrzt5...");

        client.update_score(&farm_id, &150, &tx_id, &evidence_cid); // Score inválido
    }
}
