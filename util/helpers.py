from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import locale
import os
from io import BytesIO
import io
from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak)
from datetime import datetime, timedelta
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm

def calcular_parcelas_neon(data_compra, quantidade_parcelas, vencimento_dia, melhor_dia_compra):
    # O mês base para vencimento é o mês seguinte ao mês da compra
    mes_base = (data_compra.replace(day=1) + relativedelta(months=1))

    # Se a compra foi depois do melhor dia, o vencimento começa nesse mês base
    # Caso contrário, começa no mês base anterior (ou seja, fatura atual)
    if data_compra.day <= melhor_dia_compra:
        mes_base = mes_base - relativedelta(months=1)

    try:
        primeira_parcela = mes_base.replace(day=vencimento_dia)
    except ValueError:
        proximo_mes = mes_base + relativedelta(months=1, day=1)
        primeira_parcela = proximo_mes - relativedelta(days=1)

    parcelas = [primeira_parcela + relativedelta(months=i) for i in range(quantidade_parcelas)]
    return parcelas


def calcular_parcelas_padrao(data_compra, quantidade_parcelas, vencimento_dia, melhor_dia_compra):
    if data_compra.day < melhor_dia_compra:
        primeiro_mes = data_compra + relativedelta(months=1)
    else:
        primeiro_mes = data_compra + relativedelta(months=2)

    try:
        primeira_parcela = primeiro_mes.replace(day=vencimento_dia)
    except ValueError:
        proximo_mes = primeiro_mes + relativedelta(months=1, day=1)
        primeira_parcela = proximo_mes - relativedelta(days=1)

    parcelas = []
    for i in range(quantidade_parcelas):
        parcelas.append(primeira_parcela + relativedelta(months=i))

    return parcelas


def calcular_parcelas(data_compra_str, quantidade_parcelas, vencimento_dia, melhor_dia_compra, bandeira_nome):
    try:
        data_compra = datetime.strptime(data_compra_str, "%d/%m/%Y")
    except Exception as e:
        print(f"Erro ao converter data: {data_compra_str} -> {e}")
        return []

    if "neon" in bandeira_nome.lower():
        return calcular_parcelas_neon(data_compra, quantidade_parcelas, vencimento_dia, melhor_dia_compra)
    else:
        return calcular_parcelas_padrao(data_compra, quantidade_parcelas, vencimento_dia, melhor_dia_compra)


def obter_dados_dashboard(despesas):
    totais_agrupados = defaultdict(float)

    for d in despesas:
        parcelas = calcular_parcelas(
            d['data_compra'],
            d['quantidade_parcelas'],
            d['vencimento_bandeira'],
            d['melhor_dia_compra'],
            d['bandeira_nome']
        )

        for parcela in parcelas:
            mes_ano = parcela.strftime("%m/%Y")
            bandeira = d['bandeira_nome']
            total = d['valor_parcela']
            totais_agrupados[(mes_ano, bandeira)] += total

    return [
        {'mes_ano': mes_ano, 'bandeira': bandeira, 'total': total}
        for (mes_ano, bandeira), total in totais_agrupados.items()
    ]


def calcular_totais_por_mes(parcelas_por_mes, colunas_meses):
    totais_por_mes = {}
    total_geral = 0

    for mes_ano in colunas_meses:
        total_mes = 0
        for bandeira, valores in parcelas_por_mes.items():
            total_mes += valores.get(mes_ano, 0)
        totais_por_mes[mes_ano] = total_mes
        total_geral += total_mes

    return totais_por_mes, total_geral


def converter_para_ddmmYYYY(data_str):
    try:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d')
        return data_obj.strftime('%d/%m/%Y')
    except ValueError:
        try:
            data_obj = datetime.strptime(data_str, '%d/%m/%Y')
            return data_obj.strftime('%d/%m/%Y')
        except:
            return data_str

# def converter_para_YYYYmmDD(data_str):
#     try:
#         data_obj = datetime.strptime(data_str, '%d/%m/%Y')
#         return data_obj.strftime('%Y-%m-%d')
#     except:
#         return data_str

#novas funções


# Configuração de localidade para exibir datas em português
try:
     locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')  # Linux/Mac
except:
     locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252')


def real(value):
    """Formata um número float como moeda brasileira"""
    try:
        return f"R$ {float(value):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return value
    
def init_app(app): 

 app.jinja_env.filters['real'] = real


# funçoões de calculos para o dashboard

# Função auxiliar para buscar o nome da forma de pagamento
def nome_forma_pagamento(forma_id, conn):
    resultado = conn.execute("SELECT nome FROM forma_pagamento WHERE id = ?", (forma_id,)).fetchone()
    return resultado['nome'] if resultado else 'Desconhecida'

  

    # return totais_por_mes, total_geral
def calcular_totais_por_mes(parcelas_por_mes, colunas_meses):
    totais_por_mes = {mes: 0.0 for mes in colunas_meses}
    total_geral = 0.0

     # Somar valores de todas as bandeiras para cada mês
    for bandeira, meses in parcelas_por_mes.items():
        for mes, valor in meses.items():
            valor = meses.get(mes, 0.0)
            totais_por_mes[mes] += valor
            total_geral += valor

    return totais_por_mes, total_geral

def calcular_totais_linhas(parcelas_por_mes, colunas_meses):
    totais_por_linha = {}
    for bandeira, meses in parcelas_por_mes.items():
        soma = 0.0
        for mes in colunas_meses:
            valor = meses.get(mes, 0.0)
            soma += valor
        totais_por_linha[bandeira] = soma
    return totais_por_linha

def calcular_totais_por_coluna(parcelas_por_mes, colunas_meses):
    totais_por_coluna = {mes: 0.0 for mes in colunas_meses}
    
    for bandeira, meses in parcelas_por_mes.items():
        for mes in colunas_meses:
            valor = meses.get(mes, 0.0)
            totais_por_coluna[mes] += valor
            
    total_geral = sum(totais_por_coluna.values())
    return totais_por_coluna, total_geral


#conector do banco de dados

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, 'banco', 'despesas.db')

# Função para conexão com o banco de dados
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
print(DB_PATH)


# funções de calculo de combustivel

def calcular_valor_pago(quantidade, preco):
    return round(quantidade * preco, 2)

def calcular_consumo(km, quantidade):
    return round(km / quantidade, 2) if quantidade != 0 else 0

def obter_dados_por_mes(ano, mes):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    mes_ano = f'/{mes}/{ano}'  # Exemplo: /08/2025
    cursor.execute('''
        SELECT * FROM combustivel
        WHERE data_abastecimento LIKE ?
    ''', (f'%{mes_ano}',))

 
    rows = cursor.fetchall()
    conn.close()
    return rows


# funçoes para relatorio PDF

def header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    width, height = landscape(letter)

    # Cabeçalho com logo
    import os

# Localização da imagem do logo (relativo ao app.py)
    
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))  # volta para a raiz
    logo_path = os.path.join(BASE_DIR, 'static', 'imagens', 'logo.png')
  
    canvas_obj.drawImage(logo_path, cm, height - 3.5*cm, width=4*cm, preserveAspectRatio=True)
    canvas_obj.setFont('Helvetica-Bold', 14)
    canvas_obj.drawCentredString(width / 2, height - 2.5*cm, "Relatório de Consumo de Combustível")

    # Rodapé com página
    canvas_obj.setFont('Helvetica', 9)
    page_text = f"Página {doc.page}"  # ✅ Correto

    canvas_obj.drawRightString(width - cm, cm / 2, page_text)

    canvas_obj.restoreState()


def safe_float(valor):
    if isinstance(valor, float):
        return valor
    if isinstance(valor, str):
        valor = valor.replace('.', '').replace(',', '.')
        try:
            return float(valor)
        except ValueError:
            return 0.0
    return 0.0

def parse_float_br(value):
    if isinstance(value, float):
        return value
    try:
        return float(value.replace(',', '.'))
    except (ValueError, AttributeError):
        return 0.0  # ou outro valor padrão
