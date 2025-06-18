import sqlite3

def migrar_parcelas_com_fk(db_name="despesas.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Ativa o suporte a foreign keys (sempre que abrir conexão)
    cursor.execute("PRAGMA foreign_keys = ON;")

    try:
        # 1. Criar tabela nova com foreign key
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS PARCELAS_nova (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            despesa_id INTEGER,
            numero_parcela INTEGER,
            data_vencimento DATE,
            valor_parcela REAL,
            FOREIGN KEY (despesa_id) REFERENCES DESPESAS(id)
        );
        """)

        # 2. Copiar dados da tabela antiga para a nova
        cursor.execute("""
        INSERT INTO PARCELAS_nova (id, despesa_id, numero_parcela, data_vencimento, valor_parcela)
        SELECT id, despesa_id, numero_parcela, data_vencimento, valor_parcela FROM PARCELAS;
        """)

        # 3. Apagar tabela antiga
        cursor.execute("DROP TABLE PARCELAS;")

        # 4. Renomear tabela nova para o nome original
        cursor.execute("ALTER TABLE PARCELAS_nova RENAME TO PARCELAS;")

        conn.commit()
        print("Migração concluída com sucesso. Foreign key adicionada na tabela PARCELAS.")

    except sqlite3.Error as e:
        print(f"Erro durante migração: {e}")
        conn.rollback()

    finally:
        conn.close()

if __name__ == "__main__":
    migrar_parcelas_com_fk()
