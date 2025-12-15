from db import DB_PATH
import sqlite3

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class CreditoSalarial:
    @staticmethod
    def listar_todos():
        conn = get_db_connection()
        creditos = conn.execute("SELECT * FROM SALARIO_MES").fetchall()
        conn.close()
        return creditos
