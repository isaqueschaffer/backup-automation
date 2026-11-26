SELECT 
    i.itemid,       -- ID do item
    i.hostid,       -- ID do host ao qual o item pertence
    i.name,         -- Nome do item
    i.key_,         -- Chave do item
    i.value_type,   -- Tipo de valor do item
    i.units,        -- Unidades do item
    i.discover,     -- Coluna 'discover' (se relevante)
    i.allow_traps,  -- Permissão para traps (se aplicável)
    i.uuid,         -- UUID do item
    i.lifetime_type, -- Tipo de lifetime
    i.enabled_lifetime_type, -- Tipo de lifetime habilitado
    i.enabled_lifetime -- Lifetime habilitado
    h.value AS lastvalue,       -- O valor mais recente armazenado na tabela 'history'
    CASE
        WHEN h.value > -25.9 THEN 'Bom'  -- Se o valor for maior que -25.9 dBm
        ELSE 'Ruim'                          -- Se o valor for menor ou igual a -25.9 dBm
    END AS sinal_status         -- Status do sinal (Bom ou Ruim)
FROM 
    items i
WHERE 
    i.hostid = 10657  -- Filtrando pelo hostid igual a 10657
    AND i.name LIKE 'FHTT%'  -- Filtrando pelo nome que começa com 'FHTT'
    AND i.units = 'dBm';



--------------------------------------------------------------------------------------------


SELECT       
    i.name,             
    h.value AS lastvalue,       
    CASE
        WHEN h.value > -25.9 THEN 'Bom'  
        ELSE 'Ruim'                          
    END AS sinal_status        
FROM 
    items i
JOIN history h ON h.itemid = i.itemid
WHERE 
    i.hostid = 10657  
    AND i.name LIKE 'FHTT%'  
    AND i.units = 'dBm'
    AND h.clock = (SELECT MAX(h2.clock) FROM history h2 WHERE h2.itemid = i.itemid); 