import sqlite3
import os
from collections import defaultdict
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(__file__), 'banco', 'despesas.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def inicializar_banco():
    # Conexão com o SQLite
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # permite acessar colunas por nome
    criar_tabela(conn)
    return conn


def criar_tabela(conn):
    cursor = conn.cursor()

    # Habilita suporte a Foreign Keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Script de criação das tabelas
    script_sql = """
    -- Tabelas de referência geográfica
    CREATE TABLE IF NOT EXISTS UF (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sigla TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS CIDADE (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      uf_id INTEGER NOT NULL,
      FOREIGN KEY (uf_id) REFERENCES UF(id),
      UNIQUE(nome, uf_id)
    );

    CREATE TABLE IF NOT EXISTS BAIRRO (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      cidade_id INTEGER NOT NULL,
      FOREIGN KEY (cidade_id) REFERENCES CIDADE(id),
      UNIQUE(nome, cidade_id)
    );

    CREATE TABLE IF NOT EXISTS ENDERECO (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      logradouro TEXT NOT NULL,
      numero TEXT,
      cep TEXT,
      bairro_id INTEGER NOT NULL,
      estabelecimento_id INTEGER UNIQUE,

      FOREIGN KEY (bairro_id) REFERENCES BAIRRO(id),
      FOREIGN KEY (estabelecimento_id) REFERENCES ESTABELECIMENTO(id)
        ON DELETE CASCADE ON UPDATE CASCADE
    );

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

    CREATE TABLE IF NOT EXISTS PARCELAMENTO (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT CHECK(tipo IN ('Sim', 'Não')) NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS QUANTIDADE_PARCELAS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quantidade INTEGER NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS PARCELAS (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        despesa_id INTEGER,
        numero_parcela INTEGER,
        data_vencimento DATE,
        valor_parcela REAL
    );

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

    
    -- Marcações visuais por comprador/mês (por usuário)
    CREATE TABLE IF NOT EXISTS marcas_comprador_mes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        comprador TEXT NOT NULL,
        mes TEXT NOT NULL,                     -- formato 'MM/YYYY'
        marcado INTEGER NOT NULL DEFAULT 1,    -- 1 marcado, 0 desmarcado
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES usuario(id) ON DELETE CASCADE
    );

    CREATE UNIQUE INDEX IF NOT EXISTS ux_marcas_user_comprador_mes
    ON marcas_comprador_mes (user_id, comprador, mes);

    CREATE TABLE IF NOT EXISTS combustivel (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       data_abastecimento TEXT NOT NULL,
       quantidade REAL NOT NULL,
       kilometragem REAL NOT NULL,
       preco_litro REAL NOT NULL,
       valor_pago REAL,
       consumo REAL
    );

    CREATE TABLE IF NOT EXISTS TIPO (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS MANUTENCAO_AUTO (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        estabelecimento_id INTEGER,
        tipo_id INTEGER,
        produto_id INTEGER,
        fabricante TEXT,
        valor REAL,
        data_aplicacao TEXT,
        quilometragem REAL,
        observacao TEXT,
        FOREIGN KEY (estabelecimento_id) REFERENCES ESTABELECIMENTO(id),
        FOREIGN KEY (produto_id) REFERENCES PRODUTO(id),
        FOREIGN KEY (tipo_id) REFERENCES TIPO(id)
    );

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
        parcela_alterada INTEGER,
        pago INTEGER,
        parcela_id INTEGER,
        data_vencimento TEXT,
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
        FOREIGN KEY (salario_mes_id) REFERENCES SALARIO_MES(id),
        FOREIGN KEY (parcela_id) REFERENCES PARCELAS(id)
    );
    """

    cursor.executescript(script_sql)

    # Popula tabelas auxiliares
    cursor.executemany(
        "INSERT OR IGNORE INTO QUANTIDADE_PARCELAS (quantidade) VALUES (?);",
        [(i,) for i in range(1, 13)]
    )

    cursor.executemany(
        "INSERT OR IGNORE INTO PARCELAMENTO (tipo) VALUES (?);",
        [('Sim',), ('Não',)]
    )

    cursor.executemany(
        "INSERT OR IGNORE INTO TIPO (nome) VALUES (?);",
        [('Peça',), ('Serviço',)]
    )

    # Popula UF
    cursor.executemany(
        "INSERT OR IGNORE INTO UF (sigla) VALUES (?);",
        [('PE',)]
    )

    # Obtém o ID de Pernambuco
    cursor.execute("SELECT id FROM UF WHERE sigla = 'PE'")
    uf_id = cursor.fetchone()

    # Definição de cidades da Região Metropolitana do Recife e seus respectivos bairros
    cidades_bairros = {
        "Recife": [
            "Afogados", "Água Fria", "Aflitos", "Alto do Mandu", "Alto do Pascoal",
            "Alto José Bonifácio", "Alto José do Pinho", "Alto Santa Terezinha",
            "Arruda", "Barro", "Beberibe", "Boa Viagem", "Boa Vista", "Bongi",
            "Brasília Teimosa", "Cajueiro", "Campina do Barreto", "Campo Grande",
            "Casa Amarela", "Casa Forte", "Caxangá", "Cohab", "Coelhos", "Cordeiro",
            "Derby", "Dois Irmãos", "Dois Unidos", "Encruzilhada", "Engenho do Meio",
            "Espinheiro", "Estância", "Fundão", "Graças", "Hipódromo", "Ibura",
            "Ilha do Leite", "Ilha Joana Bezerra", "Imbiribeira", "Ipsep",
            "Jaqueira", "Jardim São Paulo", "Jiquiá", "Jordão", "Linha do Tiro",
            "Macaxeira", "Madalena", "Mangabeira", "Mangueira", "Monteiro",
            "Morro da Conceição", "Mustardinha", "Paissandu", "Parnamirim",
            "Peixinhos (Recife)", "Pina", "Poço da Panela", "Ponto de Parada",
            "Porto da Madeira", "Prado", "Santana", "Sancho", "San Martin",
            "Santo Amaro", "Santo Antônio", "São José", "Setúbal", "Sítio dos Pintos",
            "Soledade", "Tamarineira", "Torre", "Torreão", "Torrões", "Totó",
            "Várzea", "Vasco da Gama", "Zumbi"
        ],
        "Olinda": [
            "Bairro Novo", "Bairro Novo do Carmo", "Bairro Novo de Olinda",
            "Bonsucesso", "Bultrins", "Caixa D'Água", "Carmo",
            "Casa Caiada", "Cidade Tabajara", "Fragoso", "Guadalupe",
            "Jardim Atlântico", "Jardim Fragoso", "Ouro Preto",
            "Peixinhos", "Rio Doce", "Santa Teresa", "Sítio Novo",
            "Varadouro"
        ],
        "Jaboatão dos Guararapes": [
            "Barra de Jangada", "Bulhões", "Cajueiro Seco", "Candeias", "Carneiros",
            "Cascata", "Cavaleiro", "Centro", "Comportas", "Curado", "Dois Carneiros",
            "Engenho Velho", "Jardim Jordão", "Jardim Piedade", "Jardim São Paulo (Jaboatão)",
            "Manassu", "Marcos Freire", "Pacheco", "Piedade", "Prazeres", "Socorro",
            "Sucupira", "Vargem Fria", "Vila Rica", "Vista Alegre", "Área Rural de Jaboatão dos Guararapes"
        ],
        "Paulista": [
            "Janga", "Maranguape I", "Maranguape II", "Nossa Senhora do Ó",
            "Paratibe", "Pau Amarelo", "Várzea Fria", "Mirueira",
            "Engenho Maranguape"
        ],
        "Camaragibe": [
            "Aldeia", "Bairro Novo do Carmelo", "Centro", "São João e São Paulo",
            "Timbi", "Santa Mônica", "Vera Cruz"
        ],
        "São Lourenço da Mata": [
            "Centro", "Pixete", "Coqueiral", "Tiúma", "Penedo", "Várzea Fria"
        ],
        "Abreu e Lima": [
            "Abreu e Lima"
        ],
        "Araçoiaba": [
            "Araçoiaba"
        ],
        "Cabo de Santo Agostinho": [
            "Cabo de Santo Agostinho", "Juçaral", "Ponte dos Carvalhos", "Santo Agostinho"
        ],
        "Igarassu": [
            "Igarassu", "Nova Cruz", "Três Ladeiras"
        ],
        "Ipojuca": [
            "Ipojuca", "Suape"
        ],
        "Itapissuma": [
            "Itapissuma"
        ],
        "Moreno": [
            "Moreno"
        ],
        "Goiana": [
            "Goiana"
        ],
        "Ilha de Itamaracá": [
            "Itamaracá"
        ]
    }

    # Obtém o ID de Pernambuco
    cursor.execute("SELECT id FROM UF WHERE sigla = 'PE'")
    row = cursor.fetchone()
    if not row:
       raise ValueError("UF 'PE' não encontrada")
    uf_id = row['id']  #
    # Insere cidades e seus bairros
    for cidade_nome, bairros in cidades_bairros.items():
        cursor.execute(
            "INSERT OR IGNORE INTO CIDADE (nome, uf_id) VALUES (?, ?)",
            (cidade_nome, uf_id)
        )
        cursor.execute("SELECT id FROM CIDADE WHERE nome = ? AND uf_id = ?", (cidade_nome, uf_id))
        row = cursor.fetchone()
        if not row:
         continue  # cidade não encontrada (não deveria acontecer, mas é bom tratar)
        cidade_id = row['id']  # ou row

       
        # Insere bairros da cidade
        for bairro_nome in bairros:
            cursor.execute(
                "INSERT OR IGNORE INTO BAIRRO (nome, cidade_id) VALUES (?, ?)",
                (bairro_nome, cidade_id)
            )

    conn.commit()
    conn.close()
    print(f"Banco de dados '{DB_PATH}' criado com sucesso!")
    print("✅ Banco carregado com 15 cidades da Região Metropolitana do Recife")
    print("✅ Tabelas CIDADE e BAIRRO vinculadas corretamente.")


if __name__ == "__main__":
    conn = inicializar_banco()
    conn.close()
