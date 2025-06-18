import sqlite3

def inicializar_banco(db_name="despesas.db"):
    # Conexão com o SQLite
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Habilita suporte a Foreign Keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Script de criação das tabelas
    script_sql = """
    -- Tabelas principais de referência
    CREATE TABLE IF NOT EXISTS ESTABELECIMENTO (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS CATEGORIA (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS LOCAL_COMPRA (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS PRODUTO (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS COMPRADOR (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS FORMA_PAGAMENTO (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS BANDEIRA (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        melhor_dia_compra INTEGER,
        vencimento INTEGER
    );

    -- Tipo booleano representado por texto "Sim" ou "Não"
    CREATE TABLE IF NOT EXISTS PARCELAMENTO (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT CHECK(tipo IN ('Sim', 'Não')) NOT NULL UNIQUE
    );

    -- Tabelas auxiliares
    CREATE TABLE IF NOT EXISTS QUANTIDADE_PARCELAS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quantidade INTEGER NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS PARCELAS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        despesa_id INTEGER,
        numero_parcela INTEGER,
        data_vencimento DATE,
        valor_parcela REAL );

    CREATE TABLE IF NOT EXISTS SALARIO_MES (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        DATA_DO_CREDITO DATE,
        VALOR_SALARIO REAL
    );

        
    CREATE TABLE IF NOT EXISTS usuario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE NOT NULL,
        senha_hash TEXT NOT NULL
    
     );

    

    -- Tabela principal
    CREATE TABLE IF NOT EXISTS DESPESAS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estabelecimento_id INTEGER,
        categoria_id INTEGER,
        local_compra_id INTEGER,
        comprador_id INTEGER,
        produto_id INTEGER,
        data_compra TEXT,
        valor_compra REAL,
        forma_pagamento_id INTEGER,
        bandeira_id INTEGER,
        parcelamento_id INTEGER,
        quantidade_parcelas_id INTEGER,
        valor_parcela REAL,
        salario_mes_id INTEGER,
        parcela_alterada INTERGER,
        pago INTERGER,
        observacao TEXT,

        FOREIGN KEY (estabelecimento_id) REFERENCES ESTABELECIMENTO(id),
        FOREIGN KEY (categoria_id) REFERENCES CATEGORIA(id),
        FOREIGN KEY (local_compra_id) REFERENCES LOCAL_COMPRA(id),
        FOREIGN KEY (comprador_id) REFERENCES COMPRADOR(id),
        FOREIGN KEY (produto_id) REFERENCES PRODUTO(id),
        FOREIGN KEY (forma_pagamento_id) REFERENCES FORMA_PAGAMENTO(id),
        FOREIGN KEY (bandeira_id) REFERENCES BANDEIRA(id),
        FOREIGN KEY (parcelamento_id) REFERENCES PARCELAMENTO(id),
        FOREIGN KEY (quantidade_parcelas_id) REFERENCES QUANTIDADE_PARCELAS(id),
        FOREIGN KEY (salario_mes_id) REFERENCES SALARIO_MES(id)
    );
    """

    # Executa o script SQL
    cursor.executescript(script_sql)

    # Popula as tabelas auxiliares com valores padrão
    cursor.executemany(
        "INSERT OR IGNORE INTO QUANTIDADE_PARCELAS (quantidade) VALUES (?);",
        [(i,) for i in range(1, 13)]
    )

    cursor.executemany(
       "INSERT OR IGNORE INTO PARCELAMENTO (tipo) VALUES (?);",
        [('Sim',), ('Não',)]
    )

   
    # Fechar conexão
    conn.commit()
    conn.close()
    print(f"Banco de dados '{db_name}' criado com sucesso e tabelas auxiliares populadas.")

# Se quiser rodar este script separadamente
if __name__ == "__main__":
    inicializar_banco()
