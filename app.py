from db import inicializar_banco
inicializar_banco()

from flask import  render_template, request, redirect, url_for, flash


# ----------------------------
# Bibliotecas padrão
# ----------------------------

import os
import io
import calendar
import csv
import sqlite3
import locale
from datetime import datetime
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from io import BytesIO
# ----------------------------
# Flask e extensões
# ----------------------------
from flask import(Flask, render_template, request, redirect, url_for, flash, session, jsonify,  make_response, render_template, Response )
from flask_wtf.csrf import CSRFProtect,  generate_csrf,  CSRFError
# ----------------------------
# Segurança
# ----------------------------
from werkzeug.security import generate_password_hash, check_password_hash

# ----------------------------
# ReportLab (PDF)
# ----------------------------
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak)
from datetime import datetime, timedelta
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
# ----------------------------
# Importações locais
# ----------------------------
from models import CreditoSalarial  # supondo que você tenha esse model
from util.helpers import (calcular_parcelas, calcular_totais_por_mes, converter_para_ddmmYYYY, nome_forma_pagamento, calcular_totais_linhas, calcular_totais_por_coluna, calcular_totais_linhas, real,get_db_connection, header_footer,obter_dados_por_mes,safe_float, calcular_valor_pago,calcular_consumo,parse_float_br )






app = Flask(__name__)
app.jinja_env.filters['real'] = real
app.config['SECRET_KEY'] = 'despesas'  
csrf = CSRFProtect(app)


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('Erro de segurança: token CSRF inválido ou expirado. Recarregue a página e tente novamente.', 'danger')
    return redirect(request.url)

#DB = 'despesas.db'


@app.route('/toggle_pagamento', methods=['POST'])
def toggle_pagamento_ajax():
    data = request.get_json()
    bandeira = data.get('bandeira')
    mes_ano = data.get('mes_ano')  # formato "mm/YYYY"
   
    print(f"Dados recebidos no toggle: bandeira='{bandeira}', mes_ano='{mes_ano}'") 
   
    if not bandeira or not mes_ano:
        return jsonify({'success': False, 'error': 'Parâmetros insuficientes'}), 400
    
    bandeira_param = bandeira.split(' - ')[0] + '%'

    try:
        dt = datetime.strptime(mes_ano, "%m/%Y")
        mes = f"{dt.month:02d}"
        ano = str(dt.year)
     
       
    
        conn = get_db_connection()
        parcelas = conn.execute("""
            SELECT P.id, P.pago
            FROM parcelas P
            JOIN despesas D ON P.despesa_id = D.id
            JOIN bandeira B ON D.bandeira_id = B.id
            WHERE B.nome LIKE ?
            AND substr(P.data_vencimento, 4, 2) = ?  
            AND substr(P.data_vencimento, 7, 4) = ?  
        """, (bandeira_param, mes, ano)).fetchall()  # -- (bandeira, f"{mes:02d}", str(ano))).fetchall()
       
        print(f"Parcelas encontradas: {len(parcelas)}")  # Debug


        if not parcelas:
            conn.close()
            return jsonify({'success': False, 'error': 'Nenhuma parcela encontrada'}), 404

        todas_pagas = all(bool(p['pago']) for p in parcelas)
        novo_status = 0 if todas_pagas else 1  # SQLite usa 0/1 para False/True

         
        for p in parcelas:
            print(f"Atualizando parcela {p['id']} para pago={novo_status}")
            conn.execute(
                "UPDATE parcelas SET pago = ? WHERE id = ?",
                (novo_status, p['id'])
            )
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'pago': novo_status == 1})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

#-------------------Rota para Dashboard ---------------------

@app.route('/')
def dashboard():
    tempo_atualizacao_segundos = 15 
  
# Simulando que você recebeu do frontend (ex: via POST, GET, cookie, etc)
    tempo_atualizacao_usuario = request.args.get('tempo_atualizacao', None)  # ou POST

    if tempo_atualizacao_usuario is not None:
        try:
            tempo_atualizacao_segundos = int(tempo_atualizacao_usuario)
            if tempo_atualizacao_segundos == 0:
            # Desliga atualização automática
               tempo_atualizacao_segundos = None
        except ValueError:
             pass



    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()

    # Obter mês selecionado da query string, padrão mês atual
    mes_selecionado = request.args.get('mes', datetime.now().strftime("%m/%Y"))
    # Totais por comprador e mês (para nova seção)
    comprador_mes_raw = conn.execute("""
        SELECT 
            COALESCE(C.nome, 'Não especificado') AS comprador,
            strftime('%m/%Y', 
                substr(D.data_compra, 7, 4) || '-' || substr(D.data_compra, 4, 2) || '-' || substr(D.data_compra, 1, 2)
            ) AS mes_ano,
            SUM(D.valor_compra) AS total
        FROM despesas D
        LEFT JOIN comprador C ON D.comprador_id = C.id
        WHERE D.data_compra IS NOT NULL
            AND length(D.data_compra) = 10
            AND UPPER(COALESCE(C.nome, 'Não especificado')) != 'ALEXANDRE'                               
        GROUP BY comprador, mes_ano
        ORDER BY comprador, mes_ano
    """).fetchall()

    # Converter para dicionário: {comprador: {mes: total}}
    from collections import defaultdict
    totais_por_comprador_mes = defaultdict(dict)
    meses_compradores = set()

    for row in comprador_mes_raw:
        comprador = row['comprador']
        mes = row['mes_ano']
        total = float(row['total'])
        totais_por_comprador_mes[comprador][mes] = total
        if mes is not None:
            meses_compradores.add(mes)

    # Ordenar os meses para usar no template
    colunas_meses_compradores = sorted(meses_compradores, key=lambda x: datetime.strptime(x, "%m/%Y"))
    
    # Ajuste aqui conforme seu ID real de forma_pagamento que representa cartão de crédito
    CARTAO_CREDITO_ID = 2

    despesas = conn.execute("""
        SELECT 
            D.id AS despesa_id,
            D.data_compra,
            D.valor_compra,
            D.valor_parcela AS valor_parcela_despesa,
            D.parcela_alterada,
            D.pago,
            QP.quantidade AS quantidade_parcelas,
            PRD.nome AS produto_nome,
            B.nome AS bandeira_nome,
            B.vencimento_dia AS vencimento_bandeira,
            B.melhor_dia_compra AS melhor_dia_compra,
            E.nome AS estabelecimento,
            D.forma_pagamento_id,
            C.nome AS comprador_nome                     
        FROM DESPESAS D
        LEFT JOIN ESTABELECIMENTO E ON D.estabelecimento_id = E.id                        
        LEFT JOIN PRODUTO PRD ON D.produto_id = PRD.id
        LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
        LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
        LEFT JOIN COMPRADOR C ON D.comprador_id = C.id 
        ORDER BY  B.vencimento_dia  DESC
    """).fetchall()

    despesas = [dict(row) for row in despesas]

    parcelas_por_mes = defaultdict(lambda: defaultdict(float))  # Todas as despesas
    parcelas_status_pagamento = defaultdict(lambda: defaultdict(list))
    parcelas_por_mes_outros = defaultdict(lambda: defaultdict(float))  # Formas != cartão
    parcelas_status_pagamento_outros = defaultdict(lambda: defaultdict(list))
    formas_pagamento_outros = {}

    meses_set = set()
    parcelas_exibidas = []

    totais_por_comprador_mes = defaultdict(lambda: defaultdict(float))

    for despesa in despesas:
        forma_pagamento_id = despesa['forma_pagamento_id']
        valor_total = safe_float(despesa['valor_compra'])
        quantidade_parcelas = int(despesa['quantidade_parcelas'])
        data_compra_str = despesa['data_compra']
        bandeira_nome = despesa['bandeira_nome']
        vencimento_bandeira = despesa['vencimento_bandeira']
        melhor_dia_compra = despesa['melhor_dia_compra']
           
        
        # Gera a lista de todos os meses para colunas de compradores
        meses_compradores = set()
        for valores in totais_por_comprador_mes.values():
            meses_compradores.update(valores.keys())

        colunas_meses_compradores = sorted(meses_compradores, key=lambda x: datetime.strptime(x, "%m/%Y"))

        chave_bandeira = f"{bandeira_nome} - {vencimento_bandeira}"

        if bandeira_nome.lower() == 'neon':
            datas_parcelas = calcular_parcelas(
                data_compra_str,
                quantidade_parcelas,
                vencimento_bandeira,
                melhor_dia_compra,
                bandeira_nome
            )
            valor_parcela = valor_total / quantidade_parcelas
        else:
            valor_parcela = float(despesa['valor_parcela_despesa'])
            datas_parcelas = []
            parcelas_no_banco = conn.execute("""
                SELECT id, data_vencimento, pago
                FROM parcelas 
                WHERE despesa_id = ?
                ORDER BY data_vencimento
            """, (despesa['despesa_id'],)).fetchall()

        if bandeira_nome.lower() == 'neon':
            for idx, dt_vencimento in enumerate(datas_parcelas, start=1):
                mes_ano = dt_vencimento.strftime("%m/%Y")
                comprador_nome = (despesa.get('comprador_nome') or "Não especificado").strip()
                if comprador_nome.upper() != 'ALEXANDRE':
                    totais_por_comprador_mes[comprador_nome][mes_ano] += valor_parcela
                meses_set.add(mes_ano)

                parcela_db = conn.execute("""
                    SELECT id, pago FROM parcelas
                    WHERE despesa_id = ? AND numero_parcela = ?
                """, (despesa['despesa_id'], idx)).fetchone()
                pago_parcela = int(parcela_db['pago'] if parcela_db else 0)

                chave_bandeira = f"{bandeira_nome} - {vencimento_bandeira}"

                # Adiciona ao total geral
                if forma_pagamento_id == CARTAO_CREDITO_ID:
                    parcelas_por_mes[chave_bandeira][mes_ano] += valor_parcela
                    parcelas_status_pagamento[chave_bandeira][mes_ano].append(pago_parcela)

                else:  # Adiciona ao total filtrado (formas de pagamento diferentes de cartão)
                    parcelas_por_mes_outros[chave_bandeira][mes_ano] += valor_parcela
                    parcelas_status_pagamento_outros[chave_bandeira][mes_ano].append(pago_parcela)

                    # Guardar forma de pagamento
                    if chave_bandeira not in formas_pagamento_outros:
                        formas_pagamento_outros[chave_bandeira] = nome_forma_pagamento(forma_pagamento_id, conn)

                parcelas_exibidas.append({
                    "id": despesa['despesa_id'],
                    "numero_parcela": idx,
                    "total_parcelas": quantidade_parcelas,
                    "data_vencimento": dt_vencimento,
                    "valor_parcela": valor_parcela,
                    "parcela_alterada": bool(despesa.get("parcela_alterada", 0)),
                    "produto_nome": despesa['produto_nome'],
                    "bandeira_nome": bandeira_nome,
                    "estabelecimento": despesa['estabelecimento'],
                    "data_compra": despesa['data_compra'],
                    "pago": pago_parcela
                })
        else:
            for idx, parcela in enumerate(parcelas_no_banco, start=1):
                vencimento_str = parcela['data_vencimento']
                dt_vencimento = datetime.strptime(vencimento_str, "%d/%m/%Y")
                mes_ano = dt_vencimento.strftime("%m/%Y")
                comprador_nome = (despesa.get('comprador_nome') or "Não especificado").strip()
                if comprador_nome.upper() != 'ALEXANDRE':
                    totais_por_comprador_mes[comprador_nome][mes_ano] += valor_parcela
                meses_set.add(mes_ano)

                pago_parcela = int(parcela['pago'] or 0)
                
                if forma_pagamento_id == CARTAO_CREDITO_ID:
                    parcelas_por_mes[chave_bandeira][mes_ano] += valor_parcela
                    parcelas_status_pagamento[chave_bandeira][mes_ano].append(pago_parcela)
                else:
                    parcelas_por_mes_outros[chave_bandeira][mes_ano] += valor_parcela
                    parcelas_status_pagamento_outros[chave_bandeira][mes_ano].append(pago_parcela)
                    
                    if chave_bandeira not in formas_pagamento_outros:
                        formas_pagamento_outros[chave_bandeira] = nome_forma_pagamento(forma_pagamento_id, conn)

                parcelas_exibidas.append({
                    "id": despesa['despesa_id'],
                    "numero_parcela": idx,
                    "total_parcelas": quantidade_parcelas,
                    "data_vencimento": dt_vencimento,
                    "valor_parcela": valor_parcela,
                    "parcela_alterada": bool(despesa.get("parcela_alterada", 0)),
                    "produto_nome": despesa['produto_nome'],
                    "bandeira_nome": bandeira_nome,
                    "estabelecimento": despesa['estabelecimento'],
                    "data_compra": despesa['data_compra'],
                    "comprador_nome": despesa['comprador_nome'],
                    "pago": pago_parcela
                })

    pagamento_por_mes_bandeira = {
        bandeira: {
            mes: all(bool(p) for p in pagamentos)
            for mes, pagamentos in meses.items()
        }
        for bandeira, meses in parcelas_status_pagamento.items()
    }

    pagamento_por_mes_bandeira_outros = {
        bandeira: {
            mes: all(bool(p) for p in pagamentos)
            for mes, pagamentos in meses.items()
        }
        for bandeira, meses in parcelas_status_pagamento_outros.items()
    }

    colunas_meses = sorted(meses_set, key=lambda x: datetime.strptime(x, "%m/%Y"))
    totais_por_mes, total_geral = calcular_totais_por_mes(parcelas_por_mes, colunas_meses)
    totais_por_mes_outros, total_geral_outros = calcular_totais_por_mes(parcelas_por_mes_outros, colunas_meses)

    # Aí você insere esse novo cálculo para totais por linha
    totais_por_linha = {}
    for bandeira, meses in parcelas_por_mes.items():
        soma_bandeira = 0.0
        for mes in colunas_meses:
            valor = meses.get(mes, 0.0)
            soma_bandeira += valor
        totais_por_linha[bandeira] = soma_bandeira

    totais_por_linha = calcular_totais_linhas(parcelas_por_mes, colunas_meses)
    totais_por_linha_outros = calcular_totais_linhas(parcelas_por_mes_outros, colunas_meses)

    totais_por_coluna, total_geral_colunas = calcular_totais_por_coluna(parcelas_por_mes, colunas_meses)
    totais_por_coluna_outros, total_geral_colunas_outros = calcular_totais_por_coluna(parcelas_por_mes_outros, colunas_meses)

    # Depois de montar totais_por_comprador_mes, antes do return render_template:
    totais_por_mes_comprador = defaultdict(float)

    for comprador, meses in totais_por_comprador_mes.items():
        for mes, total in meses.items():
            totais_por_mes_comprador[mes] += total

    total_geral_compradores = sum(totais_por_mes_comprador.values())

    mes_atual = datetime.now().strftime("%m/%Y")

    cursor = conn.execute("""
        SELECT SUM(VALOR_SALARIO) as total
        FROM salario_mes
        WHERE strftime('%m/%Y', substr(DATA_DO_CREDITO, 7, 4) || '-' || substr(DATA_DO_CREDITO, 4, 2) || '-' || substr(DATA_DO_CREDITO, 1, 2)) = ?
    """, (mes_atual,))
    resultado = cursor.fetchone()
    total_creditos_mes = float(resultado["total"] or 0.0)

    # Função interna para somar parcelas por mês
    def somar_parcelas(parcelas1, parcelas2):
        resultado = defaultdict(float)

        for bandeira, meses in parcelas1.items():
            for mes, valor in meses.items():
                resultado[mes] += valor

        for bandeira, meses in parcelas2.items():
            for mes, valor in meses.items():
                resultado[mes] += valor

        return dict(resultado)

    totais_por_mes_soma = somar_parcelas(parcelas_por_mes, parcelas_por_mes_outros)

    # Atualizar o total de despesas para o mês selecionado
    total_despesas_mes = totais_por_mes_soma.get(mes_selecionado, 0.0)

    cursor = conn.execute("""
        SELECT SUM(VALOR_SALARIO) as total
        FROM salario_mes
        WHERE strftime('%m/%Y', substr(DATA_DO_CREDITO, 7, 4) || '-' || substr(DATA_DO_CREDITO, 4, 2) || '-' || substr(DATA_DO_CREDITO, 1, 2)) = ?
    """, (mes_selecionado,))
    resultado = cursor.fetchone()
    total_creditos_mes = float(resultado["total"] or 0.0)
    credito_compradores = totais_por_mes_comprador.get(mes_selecionado, 0.0)


    # saldo_mes = total_creditos_mes - total_despesas_mes
    saldo_mes = (total_creditos_mes + credito_compradores) - total_despesas_mes

    # Aqui você insere a consulta para o valor pago:
    valor_pago_mes = conn.execute("""
        SELECT SUM(P.valor_parcela) as total_pago
        FROM parcelas P
        JOIN despesas D ON P.despesa_id = D.id
        WHERE P.pago = 1
          AND strftime('%m/%Y', substr(P.data_vencimento, 7, 4) || '-' || substr(P.data_vencimento, 4, 2) || '-' || substr(P.data_vencimento, 1, 2)) = ?
    """, (mes_selecionado,)).fetchone()

    total_pago_mes = float(valor_pago_mes['total_pago'] or 0.0)
  
    # Cálculo do saldo
    saldo_mes_ajustado = total_pago_mes - total_despesas_mes  

    csrf_token = generate_csrf()
    conn.close()

    # Corrige arredondamento de zero
    if abs(saldo_mes) < 0.01:
     saldo_mes = 0.0
    if abs(saldo_mes_ajustado) < 0.01:
     saldo_mes_ajustado = 0.0
    if abs(total_pago_mes) < 0.01:
     total_pago_mes = 0.0


   # credito_compradores = valor_compradores  # já existe esse valor
    credito_compradores = totais_por_mes_comprador.get(mes_selecionado, 0.0)
 
    creditos_do_mes = total_creditos_mes + credito_compradores
# NOVO: Montar se todas as parcelas de cada comprador em cada mês estão pagas
    pagamento_por_mes_comprador = {
       comprador: {
        mes: all(
            parcela.get("pago", 0) == 1
            for parcela in parcelas_exibidas
            if parcela["data_vencimento"].strftime("%m/%Y") == mes
            and (parcela.get('comprador_nome') or "Não especificado").strip() == comprador
        )
        for mes in colunas_meses_compradores
    }
    for comprador in totais_por_comprador_mes
}




    for comprador, meses in pagamento_por_mes_comprador.items():
      for mes, pago in meses.items():
        print(f"Comprador: {comprador} | Mês: {mes} | Pago: {pago} | Valores: {pagamento_por_mes_comprador[comprador][mes]}")


    #print('totais_por_mes_comprador:', totais_por_mes_comprador)
    return render_template(
        'dashboard.html',
       
        tempo_atualizacao=tempo_atualizacao_segundos,
        parcelas=parcelas_exibidas,
        parcelas_por_mes=parcelas_por_mes,
        parcelas_por_mes_outros=parcelas_por_mes_outros,
        colunas_meses=colunas_meses,
        totais_por_mes=totais_por_mes,
        totais_por_mes_outros=totais_por_mes_outros,
        totais_por_linha=totais_por_linha,
        totais_por_linha_outros=totais_por_linha_outros,
        totais_por_coluna=totais_por_coluna,
        totais_por_coluna_outros=totais_por_coluna_outros,
        total_geral_colunas=total_geral_colunas,
        total_geral_colunas_outros=total_geral_colunas_outros,
        total_geral=total_geral,
        total_geral_outros=total_geral_outros,
        credito_compradores=credito_compradores,
        creditos_do_mes=creditos_do_mes,
        pagamento_por_mes_bandeira=pagamento_por_mes_bandeira,
        pagamento_por_mes_bandeira_outros=pagamento_por_mes_bandeira_outros,
        pagamento_por_mes_comprador=pagamento_por_mes_comprador,     
        formas_pagamento_outros=formas_pagamento_outros,
        totais_por_comprador_mes=totais_por_comprador_mes,
        colunas_meses_compradores=colunas_meses_compradores,
        total_geral_compradores=total_geral_compradores,
        totais_por_mes_comprador=totais_por_mes_comprador,
        total_creditos_mes=total_creditos_mes,
        total_despesas_mes=total_despesas_mes,
        saldo_mes=saldo_mes,
        total_pago_mes=total_pago_mes,
        saldo_mes_ajustado=saldo_mes_ajustado,
        mes_selecionado=mes_selecionado,
        csrf_token=csrf_token
    )

@app.route('/rota_de_atualizacao')
def rota_de_atualizacao():
    # código para retornar alguma resposta
    return "Rota de atualização funcionando"


@app.route('/dashboard_analytics')
def dashboard_analytics():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    # Parâmetro para tempo de atualização (em segundos), default 15
    tempo_atualizacao_segundos = 15
    tempo_atualizacao_usuario = request.args.get('tempo_atualizacao', None)
    if tempo_atualizacao_usuario is not None:
        try:
            tempo_atualizacao_segundos = int(tempo_atualizacao_usuario)
            if tempo_atualizacao_segundos == 0:
                tempo_atualizacao_segundos = None  # desliga atualização automática
        except ValueError:
            pass

    # Buscar estabelecimentos para o filtro, com id e nome
    estabelecimentos = conn.execute("""
        SELECT id, COALESCE(nome, 'Não especificado') AS nome
        FROM estabelecimento
        ORDER BY nome
    """).fetchall()

    # Consultas agregadas (totais por Estabelecimento, Produto, Bandeira, Comprador e Mês)

    # Totais por Estabelecimento
    totais_estab = conn.execute("""
        SELECT
            E.id AS estabelecimento_id,
            COALESCE(E.nome, 'Não especificado') AS estabelecimento,
            SUM(D.valor_compra) AS total
        FROM despesas D
        LEFT JOIN estabelecimento E ON D.estabelecimento_id = E.id
        GROUP BY E.id, estabelecimento
        ORDER BY total DESC
    """).fetchall()

    # Totais por Produto
    produtos = conn.execute("""
        SELECT
            P.id AS produto_id,
            COALESCE(P.nome, 'Não especificado') AS produto,
            SUM(D.valor_compra) AS total
        FROM despesas D
        LEFT JOIN produto P ON D.produto_id = P.id
        GROUP BY P.id, produto
        ORDER BY total DESC
    """).fetchall()

    # Totais por Bandeira
    bandeiras = conn.execute("""
        SELECT
            B.id AS bandeira_id,
            COALESCE(B.nome, 'Não especificado') AS bandeira,
            SUM(D.valor_compra) AS total
        FROM despesas D
        LEFT JOIN bandeira B ON D.bandeira_id = B.id
        GROUP BY B.id, bandeira
        ORDER BY total DESC
    """).fetchall()

    # Totais por Comprador
    compradores = conn.execute("""
        SELECT
            C.id AS comprador_id,
            COALESCE(C.nome, 'Não especificado') AS comprador,
            SUM(D.valor_compra) AS total
        FROM despesas D
        LEFT JOIN comprador C ON D.comprador_id = C.id
        GROUP BY C.id, comprador
        ORDER BY total DESC
    """).fetchall()

    # Totais por Mês (formatado MM/YYYY)
    meses = conn.execute("""
        SELECT
            strftime('%m/%Y', substr(D.data_compra, 7, 4) || '-' || substr(D.data_compra, 4, 2) || '-' || substr(D.data_compra, 1, 2)) AS mes_ano,
            SUM(D.valor_compra) AS total
        FROM despesas D
        WHERE D.data_compra IS NOT NULL AND length(D.data_compra) = 10
        GROUP BY mes_ano
        ORDER BY mes_ano
    """).fetchall()

    conn.close()

    # Preparar dados para o template (convertendo rows em listas de dicts)
    def to_dict_list_with_id(rows, id_key, name_key):
        # id_key: coluna de id (ex: 'estabelecimento_id'), name_key: coluna de nome (ex: 'estabelecimento' ou 'nome')
        return [
            { id_key: row[id_key], name_key: row[name_key], 'total': float(row['total'] or 0) }
            for row in rows
        ]

    estabelecimentos_lista = [
        {'id': row['id'], 'nome': row['nome']}
        for row in estabelecimentos
    ]

    totais_estab_data = to_dict_list_with_id(totais_estab, 'estabelecimento_id', 'estabelecimento')
    produtos_data = to_dict_list_with_id(produtos, 'produto_id', 'produto')
    bandeiras_data = to_dict_list_with_id(bandeiras, 'bandeira_id', 'bandeira')
    compradores_data = to_dict_list_with_id(compradores, 'comprador_id', 'comprador')
    meses_data = [
        {'mes_ano': row['mes_ano'], 'total': float(row['total'] or 0)}
        for row in meses
    ]

    return render_template(
        'dashboard_analytics.html',
        tempo_atualizacao=tempo_atualizacao_segundos,
        estabelecimentos=estabelecimentos_lista,
        totais_estab=totais_estab_data,
        produtos=produtos_data,
        bandeiras=bandeiras_data,
        compradores=compradores_data,
        meses=meses_data,
    )

@app.route('/analytics/despesas_por_estabelecimento', methods=['GET'])
def despesas_por_estabelecimento():
    if 'user_id' not in session:
        return jsonify({'error': 'Não autorizado'}), 401

    estabelecimento_id = request.args.get('estabelecimento_id', type=int)
    mes_ano = request.args.get('mes_ano', default=None, type=str)  # esperado no formato "MM/YYYY"

    if estabelecimento_id is None or mes_ano is None:
        return jsonify({'error': 'Parâmetros inválidos'}), 400

    conn = get_db_connection()

    # Buscar todas as despesas desse estabelecimento no mês/ano
    despesas = conn.execute("""
      SELECT
        D.data_compra,
        B.nome as bandeira_nome,
        D.valor_compra,
        D.valor_parcela AS valor_parcela_despesa,
        QP.quantidade AS quantidade_parcelas
    FROM despesas D
    LEFT JOIN bandeira B ON D.bandeira_id = B.id
    LEFT JOIN quantidade_parcelas QP ON D.quantidade_parcelas_id = QP.id
    WHERE D.estabelecimento_id = ?
      AND strftime('%m/%Y',
          substr(D.data_compra, 7, 4) || '-' || substr(D.data_compra, 4, 2) || '-' || substr(D.data_compra, 1, 2)
      ) = ?
    ORDER BY D.data_compra
""", (estabelecimento_id, mes_ano)).fetchall()


    # Calcular valor total para esse estabelecimento nesse mês
    total = conn.execute("""
        SELECT SUM(D.valor_compra) as total
        FROM despesas D
        WHERE D.estabelecimento_id = ?
          AND strftime('%m/%Y',
              substr(D.data_compra, 7, 4) || '-' || substr(D.data_compra, 4, 2) || '-' || substr(D.data_compra, 1, 2)
          ) = ?
    """, (estabelecimento_id, mes_ano)).fetchone()

    conn.close()

    lista = []
    for d in despesas:
     lista.append({
        'data_compra': d['data_compra'],
        'bandeira': d['bandeira_nome'],
        'valor_compra': float(d['valor_compra'] or 0),
        'quantidade_parcelas': d['quantidade_parcelas']or 0,
        'valor_parcela': float(d['valor_parcela_despesa'] or 0)
    })

    retorno = {
        'despesas': lista,
        'total': float(total['total'] or 0)
    }
    return jsonify(retorno)

@app.route('/analytics/despesas_detalhadas', methods=['GET'])
def despesas_detalhadas():
    if 'user_id' not in session:
        return jsonify({'error': 'Não autorizado'}), 401

    estabelecimento_id = request.args.get('estabelecimento_id', type=int)
    mes_ano = request.args.get('mes_ano', type=str)  # formato esperado: "MM/YYYY"

    if not estabelecimento_id or not mes_ano:
        return jsonify({'error': 'Parâmetros inválidos'}), 400

    conn = get_db_connection()

    despesas = conn.execute("""
        SELECT
            D.data_compra,
            B.nome AS bandeira_nome,
            D.valor_compra,
            D.quantidade_parcelas,
            D.valor_parcela
        FROM despesas D
        LEFT JOIN bandeira B ON D.bandeira_id = B.id
        WHERE D.estabelecimento_id = ?
          AND strftime('%m/%Y',
              substr(D.data_compra, 7, 4) || '-' || substr(D.data_compra, 4, 2) || '-' || substr(D.data_compra, 1, 2)
          ) = ?
        ORDER BY D.data_compra
    """, (estabelecimento_id, mes_ano)).fetchall()

    conn.close()

    lista_despesas = []
    for d in despesas:
        lista_despesas.append({
            'data_compra': d['data_compra'],
            'bandeira': d['bandeira_nome'],
            'valor_compra': float(d['valor_compra'] or 0),
            'quantidade_parcelas': d['quantidade_parcelas'] or 0,
            'valor_parcela': float(d['valor_parcela'] or 0),
        })

    return jsonify({'despesas': lista_despesas})

#----------------Rotas para Despesas ---------------------------




@app.route('/despesas', methods=['GET', 'POST'])
def lancar_despesas():
    conn = get_db_connection()

    if request.method == 'POST':
        print("Form data recebida:", request.form.to_dict())
        try:
            # Captura os dados do formulário
            dados = (
                request.form['estabelecimento_id'],
                request.form['categoria_id'],
                request.form['local_compra_id'],
                request.form['comprador_id'],
                request.form['produto_id'],
                request.form['data_compra'],
                request.form['valor_compra'],
                request.form['forma_pagamento_id'],
                request.form['bandeira_id'],
                request.form['parcelamento_id'],
                request.form['quantidade_parcelas_id'],
                request.form['valor_parcela'],
                request.form.get('observacao', '')
            )

            # Verifica se todos os campos foram preenchidos
           # if not all(dados):
            #    flash("Todos os campos devem ser preenchidos.", "danger")
             #   return redirect(url_for('lancar_despesas'))
            campos_obrigatorios = dados[:-1] 

            if any((v is None or str(v).strip() == '') for v in campos_obrigatorios):
               flash("Todos os campos devem ser preenchidos.", "danger")
               return redirect(url_for('lancar_despesas'))  

            cursor = conn.cursor()

          
            # ⬇️ INSERIR VERIFICAÇÃO DE DESPESA DUPLICADA AQUI
            cursor.execute("""
            SELECT COUNT(*) as count FROM DESPESAS 
            WHERE estabelecimento_id = ?
            AND categoria_id = ?
            AND local_compra_id = ?
            AND comprador_id = ?
            AND produto_id = ?
            AND data_compra = ?
            AND valor_compra = ?
            AND forma_pagamento_id = ?
            AND bandeira_id = ?
            AND parcelamento_id = ?
            AND quantidade_parcelas_id = ?
            AND valor_parcela = ?
            """, dados[:12])

            existe = cursor.fetchone()['count']

            if existe > 0:
               flash("Despesa já cadastrada com os mesmos dados.", "warning")
               conn.close()
               return redirect(url_for('lancar_despesas')) 
                
              
            # Insere a despesa (sem vencimento_bandeira_id e melhor_dia_compra_id)
            cursor.execute("""
                INSERT INTO DESPESAS (
                    estabelecimento_id, categoria_id, local_compra_id, comprador_id,
                    produto_id, data_compra, valor_compra, forma_pagamento_id, bandeira_id,
                    parcelamento_id, quantidade_parcelas_id, valor_parcela, observacao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?)
            """, dados)
            conn.commit()

            # Recupera o ID da despesa recém-inserida
            despesa_id = cursor.lastrowid

            # Obter dados para cálculo das parcelas
          #  data_compra = request.form['data_compra']  # formato: yyyy-mm-dd #####
            quantidade_parcelas = int(conn.execute(
                "SELECT quantidade FROM QUANTIDADE_PARCELAS WHERE id = ?", 
                (request.form['quantidade_parcelas_id'],)
            ).fetchone()['quantidade'])

           # bandeira_id = request.form['bandeira_id']
            bandeira_dados = conn.execute(
                "SELECT nome, melhor_dia_compra, vencimento_dia FROM BANDEIRA WHERE id = ?",
                (request.form['bandeira_id'],)
            ).fetchone()

            melhor_dia_compra = bandeira_dados['melhor_dia_compra']
            vencimento_bandeira = bandeira_dados['vencimento_dia']
            nome_bandeira = bandeira_dados['nome']
            # Converter a data de compra (YYYY-MM-DD)
            # data_compra_dt = datetime.strptime(data_compra, "%d/%m/%Y")

            # Define a data da primeira parcela com base no melhor dia de compra
            # if data_compra_dt.day < melhor_dia_compra:
            #     primeira_data = data_compra_dt.replace(day=1) + relativedelta(months=1)
            # else:
            #     primeira_data = data_compra_dt.replace(day=1) + relativedelta(months=2)

            # # Ajusta para o vencimento da fatura
            # try:
            #     primeira_data = primeira_data.replace(day=vencimento_bandeira)
            # except ValueError:
            #     ultima_do_mes = (primeira_data + relativedelta(months=1, day=1)) - relativedelta(days=1)
            #     primeira_data = ultima_do_mes

            # # Gera as datas das parcelas
            # parcelas = [primeira_data + relativedelta(months=i) for i in range(quantidade_parcelas)]

            # Inserir parcelas
           
            data_compra_str = datetime.strptime(request.form['data_compra'], "%d/%m/%Y").strftime("%d/%m/%Y")

            parcelas = calcular_parcelas(
            data_compra_str,
            quantidade_parcelas,
            vencimento_bandeira,
            melhor_dia_compra,
            nome_bandeira
        )


            for idx, vencimento in enumerate(parcelas, start=1):
                conn.execute("""
                    INSERT INTO PARCELAS (despesa_id, numero_parcela, data_vencimento, valor_parcela)
                    VALUES (?, ?, ?, ?)
                """, (despesa_id, idx, vencimento.strftime('%d/%m/%Y'), request.form['valor_parcela']))

            conn.commit()
            flash("Despesa e parcelas lançadas com sucesso!", "success")

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao lançar despesa: {str(e)}", "danger")
            print(f"Erro: {e}")

        finally:
            conn.close()

        return redirect(url_for('lancar_despesas'))
    

    # Carrega os dados para o formulário (sem vencimento_bandeira e melhor_dia_compra)
    estabelecimentos = conn.execute("SELECT * FROM ESTABELECIMENTO ORDER BY nome ASC").fetchall()
    categorias = conn.execute("SELECT * FROM CATEGORIA ORDER BY nome ASC").fetchall()
    locais = conn.execute("SELECT * FROM LOCAL_COMPRA ORDER BY nome ASC").fetchall()
    compradores = conn.execute("SELECT * FROM COMPRADOR ORDER BY nome ASC").fetchall()
    produtos = conn.execute("SELECT * FROM PRODUTO ORDER BY nome ASC").fetchall()
    formas = conn.execute("SELECT * FROM FORMA_PAGAMENTO ORDER BY nome ASC").fetchall()
    bandeiras = conn.execute("SELECT * FROM BANDEIRA ORDER BY nome ASC").fetchall()
    parcelamentos = conn.execute("SELECT * FROM PARCELAMENTO").fetchall()
    quantidade_parcelas = conn.execute("SELECT * FROM QUANTIDADE_PARCELAS").fetchall()
    conn.close()

    return render_template('Incluir_despesas.html', 
                           estabelecimentos=estabelecimentos, 
                           categorias=categorias,
                           locais=locais, 
                           compradores=compradores, 
                           produtos=produtos, 
                           formas=formas, 
                           bandeiras=bandeiras, 
                           parcelamentos=parcelamentos, 
                           quantidades=quantidade_parcelas,
                            )

@app.route('/consultar_despesas', methods=['GET', 'POST'])
def consultar_despesas():
    conn = get_db_connection()

    # Filtros recebidos via GET
    bandeira_filtro = request.args.get('bandeira', '').strip()
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()
    estabelecimento_filtro = request.args.get('estabelecimento', '').strip()
    produto_filtro = request.args.get('produto', '').strip()

    # Buscar dados para os filtros (selects)
    bandeiras = conn.execute("SELECT id, nome FROM BANDEIRA").fetchall()
    estabelecimentos = conn.execute("SELECT id, nome FROM ESTABELECIMENTO").fetchall()
    produtos = conn.execute("SELECT id, nome FROM PRODUTO").fetchall()

    # Monta a query base
    query = """
        SELECT
            D.id,
            E.nome AS estabelecimento,
            P.nome AS produto_nome,
            D.valor_compra,
            D.data_compra,
            FP.nome AS forma_pagamento,
            B.nome AS bandeira_nome,
            QP.quantidade AS numero_parcela,
            D.valor_parcela,
            D.observacao, 
            D.parcela_alterada
            FROM DESPESAS D
        LEFT JOIN PRODUTO P ON D.produto_id = P.id
        LEFT JOIN FORMA_PAGAMENTO FP ON D.forma_pagamento_id = FP.id
        LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
        LEFT JOIN ESTABELECIMENTO E ON D.estabelecimento_id = E.id
        LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
        WHERE 1=1
    """

    params = []

    # Filtro por bandeira
    if bandeira_filtro:
        query += " AND B.id = ?"
        params.append(bandeira_filtro)

    # Filtro por data de início
    if data_inicio:
        query += """
            AND (
                substr(D.data_compra, 7, 4) || substr(D.data_compra, 4, 2) || substr(D.data_compra, 1, 2)
            ) >= ?
        """
        params.append(data_inicio.replace("-", ""))

    # Filtro por data de fim
    if data_fim:
        query += """
            AND (
                substr(D.data_compra, 7, 4) || substr(D.data_compra, 4, 2) || substr(D.data_compra, 1, 2)
            ) <= ?
        """
        params.append(data_fim.replace("-", ""))

    # Filtro por estabelecimento
    if estabelecimento_filtro:
        query += " AND E.id = ?"
        params.append(estabelecimento_filtro)

    # Filtro por produto
    if produto_filtro:
        query += " AND P.id = ?"
        params.append(produto_filtro)

    # Ordenação decrescente por data_compra
    query += """
        ORDER BY substr(D.data_compra, 7, 4) || substr(D.data_compra, 4, 2) || substr(D.data_compra, 1, 2) DESC
    """

    # Debug opcional
    print("Query SQL:", query)
    print("Parâmetros:", params)

    # Executa a consulta com os filtros aplicados
    despesas = conn.execute(query, params).fetchall()
    conn.close()

    # Renderiza o template com os dados
    return render_template(
        'consultar_despesas.html',
        despesas=despesas,
        bandeiras=bandeiras,
        estabelecimentos=estabelecimentos,
        produtos=produtos,
        bandeira_selecionada=bandeira_filtro,
        estabelecimento_selecionado=estabelecimento_filtro,
        produto_selecionado=produto_filtro,
        request=request
    )

@app.route('/editar_despesa/<int:id>', methods=['GET', 'POST'])
def editar_despesa(id):
    conn = get_db_connection()

    # Busca a despesa pelo id
    despesa = conn.execute("SELECT * FROM DESPESAS WHERE id = ?", (id,)).fetchone()
    if not despesa:
        flash("Despesa não encontrada!", "danger")
        conn.close()
        return redirect(url_for('consultar_despesas'))

    if request.method == 'POST':
        print(request.form)
        try:
            # Captura dados do formulário
            estabelecimento_id = request.form['estabelecimento_id']
            categoria_id = request.form['categoria_id']
            local_compra_id = request.form['local_compra_id']
            comprador_id = request.form['comprador_id']
            produto_id = request.form['produto_id']
            data_compra_str = request.form['data_compra']
            valor_compra = request.form['valor_compra']
            forma_pagamento_id = request.form['forma_pagamento_id']
            bandeira_id = request.form['bandeira_id']
            parcelamento_id = request.form['parcelamento_id']
            quantidade_parcelas_id = request.form['quantidade_parcelas_id']
            valor_parcela = request.form['valor_parcela']
            observacao = request.form.get('observacao', '')

            parcela_alterada = 1


            valor_compra_str = request.form['valor_compra']
            valor_parcela_str = request.form['valor_parcela']

            # Substitui vírgula por ponto para poder converter para float
            valor_compra = float(valor_compra_str.replace(',', '.'))
            valor_parcela = float(valor_parcela_str.replace(',', '.'))






            # Atualiza tabela DESPESAS
            conn.execute("""
                UPDATE DESPESAS SET
                    estabelecimento_id = ?, categoria_id = ?, local_compra_id = ?, comprador_id = ?,
                    produto_id = ?, data_compra = ?, valor_compra = ?, forma_pagamento_id = ?, bandeira_id = ?,
                    parcelamento_id = ?, quantidade_parcelas_id = ?, valor_parcela = ?, observacao = ?, parcela_alterada = ?
                WHERE id = ?
            """, (
                estabelecimento_id, categoria_id, local_compra_id, comprador_id,
                produto_id, data_compra_str, valor_compra, forma_pagamento_id, bandeira_id,
                parcelamento_id, quantidade_parcelas_id, valor_parcela, observacao, parcela_alterada,
                id
            ))
            conn.commit()

            # Obtém quantidade de parcelas (int)
            nova_qtd_parcelas = conn.execute(
                "SELECT quantidade FROM QUANTIDADE_PARCELAS WHERE id = ?",
                (quantidade_parcelas_id,)
            ).fetchone()['quantidade']


            
            # Busca dados da bandeira para cálculo das datas
            bandeira_dados = conn.execute(
                "SELECT nome, melhor_dia_compra, vencimento_dia FROM BANDEIRA WHERE id = ?",
                (bandeira_id,)
            ).fetchone()

            nome_bandeira = bandeira_dados['nome']
            melhor_dia_compra = bandeira_dados['melhor_dia_compra']
            vencimento_dia = bandeira_dados['vencimento_dia']

            # Formata data da compra para padrão esperado (dd/mm/yyyy)
            data_compra_formatada = datetime.strptime(data_compra_str, "%d/%m/%Y").strftime("%d/%m/%Y")

            # Chama função externa que calcula as datas das parcelas
            datas_novas = calcular_parcelas(
                data_compra_formatada,
                nova_qtd_parcelas,
                vencimento_dia,
                melhor_dia_compra,
                nome_bandeira
            )

            # Busca parcelas atuais dessa despesa
            parcelas_existentes = conn.execute(
                "SELECT * FROM PARCELAS WHERE despesa_id = ? ORDER BY numero_parcela", (id,)
            ).fetchall()

            qtd_parcelas_atual = len(parcelas_existentes)
            novo_valor_parcela = float(valor_parcela)

            # Se precisar adicionar parcelas (nova qtd maior que atual)
            if nova_qtd_parcelas > qtd_parcelas_atual:
                for i in range(qtd_parcelas_atual, nova_qtd_parcelas):
                    conn.execute("""
                        INSERT INTO PARCELAS (despesa_id, data_vencimento, valor_parcela, numero_parcela)
                        VALUES (?, ?, ?, ?)
                    """, (id, datas_novas[i].strftime("%d/%m/%Y"), novo_valor_parcela, i + 1))

            # Se precisar remover parcelas (nova qtd menor que atual)
            elif nova_qtd_parcelas < qtd_parcelas_atual:
                for i in range(nova_qtd_parcelas, qtd_parcelas_atual):
                    conn.execute("""
                        DELETE FROM PARCELAS WHERE despesa_id = ? AND numero_parcela = ?
                    """, (id, i + 1))

            # Atualiza as parcelas que permanecem
            for i, parcela in enumerate(parcelas_existentes[:nova_qtd_parcelas]):
                conn.execute("""
                    UPDATE PARCELAS SET data_vencimento = ?, valor_parcela = ? WHERE id = ?
                """, (datas_novas[i].strftime("%d/%m/%Y"), novo_valor_parcela, parcela['id']))

            conn.commit()
            flash("Despesa atualizada com sucesso!", "success")
            conn.close()
            return redirect(url_for('consultar_despesas'))

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar despesa: {e}", "danger")
            conn.close()
            return redirect(url_for('editar_despesa', id=id))

    # Método GET - carrega dados para o formulário
    estabelecimentos = conn.execute("SELECT * FROM ESTABELECIMENTO").fetchall()
    categorias = conn.execute("SELECT * FROM CATEGORIA").fetchall()
    locais = conn.execute("SELECT * FROM LOCAL_COMPRA").fetchall()
    compradores = conn.execute("SELECT * FROM COMPRADOR").fetchall()
    produtos = conn.execute("SELECT * FROM PRODUTO").fetchall()
    formas = conn.execute("SELECT * FROM FORMA_PAGAMENTO").fetchall()
    bandeiras = conn.execute("SELECT * FROM BANDEIRA").fetchall()
    parcelamentos = conn.execute("SELECT * FROM PARCELAMENTO").fetchall()
    quantidade_parcelas = conn.execute("SELECT * FROM QUANTIDADE_PARCELAS").fetchall()

    conn.close()

    return render_template(
        'editar_despesa.html',
        despesa=despesa,
        estabelecimentos=estabelecimentos,
        categorias=categorias,
        locais=locais,
        compradores=compradores,
        produtos=produtos,
        formas=formas,
        bandeiras=bandeiras,
        parcelamentos=parcelamentos,
        quantidades=quantidade_parcelas
    )
                       
@app.route('/excluir_despesa/<int:id>', methods=['POST'])
def excluir_despesa(id):
    conn = get_db_connection()

    # Verifica se a despesa existe
    despesa = conn.execute("SELECT * FROM DESPESAS WHERE id = ?", (id,)).fetchone()

    if not despesa:
        conn.close()
        flash("Despesa não encontrada!", "danger")
        return redirect(url_for('consultar_despesas'))

    try:
        # Exclui parcelas associadas
        conn.execute("DELETE FROM PARCELAS WHERE despesa_id = ?", (id,))
        # Exclui a despesa
        conn.execute("DELETE FROM DESPESAS WHERE id = ?", (id,))
        conn.commit()
        flash("Despesa excluída com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao excluir despesa: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('consultar_despesas'))


# ------------------ Rotas do CRUD de estabelecimento -------------------------

@app.route('/cadastro/estabelecimento/novo', methods=['GET', 'POST'])
def novo_estabelecimento():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip().upper()  # Normaliza e coloca em MAIÚSCULAS

        if not nome:
            flash("O nome do estabelecimento é obrigatório.", "warning")
            return redirect(request.url)

        conn = get_db_connection()

        # Verifica duplicidade com nome em maiúsculas (garante comparação exata)
        existente = conn.execute(
            "SELECT 1 FROM ESTABELECIMENTO WHERE UPPER(TRIM(nome)) = ?", (nome,)
        ).fetchone()

        if existente:
            flash("Já existe um estabelecimento com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        try:
            conn.execute("INSERT INTO ESTABELECIMENTO (nome) VALUES (?)", (nome,))
            conn.commit()
            flash("Estabelecimento cadastrado com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Erro ao cadastrar: nome já cadastrado.", "danger")
        finally:
            conn.close()

        return redirect(url_for('listar_estabelecimentos'))

    return render_template('editar_estabelecimento.html', registro=None, tipo='estabelecimento')

@app.route('/cadastro/estabelecimento')
def consultar_estabelecimento():
    conn = get_db_connection()
    try:
        estabelecimentos = conn.execute("SELECT * FROM ESTABELECIMENTO ORDER BY nome").fetchall()
    except Exception as e:
        estabelecimentos = []
        flash(f"Erro ao consultar estabelecimentos: {str(e)}", "danger")
    finally:
        conn.close()
    return render_template('consultar_estabelecimento.html', estabelecimentos=estabelecimentos)

@app.route('/cadastro/estabelecimento/editar/<int:id>', methods=['GET', 'POST'])
def editar_estabelecimento(id):
    conn = get_db_connection()
    estabelecimento = conn.execute("SELECT * FROM ESTABELECIMENTO WHERE id = ?", (id,)).fetchone()

    if not estabelecimento:
        flash("Estabelecimento não encontrado.", "danger")
        return redirect(url_for('listar_estabelecimentos'))

    if request.method == 'POST':
        novo_nome = request.form.get('nome', '').strip().upper()  # Nome em MAIÚSCULO

        if not novo_nome:
            flash("O nome do estabelecimento é obrigatório.", "warning")
            return redirect(request.url)

        # Verifica se outro estabelecimento já usa esse nome
        duplicado = conn.execute(
            "SELECT 1 FROM ESTABELECIMENTO WHERE UPPER(TRIM(nome)) = ? AND id != ?", 
            (novo_nome, id)
        ).fetchone()

        if duplicado:
            flash("Já existe outro estabelecimento com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        conn.execute("UPDATE ESTABELECIMENTO SET nome = ? WHERE id = ?", (novo_nome, id))
        conn.commit()
        conn.close()
        flash("Estabelecimento atualizado com sucesso!", "success")
        return redirect(url_for('listar_estabelecimentos'))

    conn.close()
    return render_template('editar_estabelecimento.html', registro=estabelecimento, tipo='estabelecimento')
 # reusando o template

@app.route('/estabelecimentos')
def listar_estabelecimentos():
    conn = get_db_connection()
    estabelecimentos = conn.execute("SELECT * FROM ESTABELECIMENTO ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_estabelecimento.html', estabelecimentos=estabelecimentos)

@app.route('/estabelecimento/excluir/<int:id>', methods=['POST'])
def excluir_estabelecimento(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM ESTABELECIMENTO WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Estabelecimento excluído com sucesso!", "success")
    return redirect(url_for('listar_estabelecimentos'))




#-----------------------------Rotas do CRUD de Categoria -------------------------

@app.route('/cadastro/categoria/novo', methods=['GET', 'POST'])
def nova_categoria():
    if request.method == 'POST':
         nome = request.form.get('nome', '').strip().upper()  # Normaliza e coloca em MAIÚSCULAS
      
        
         if not nome:
            flash("O nome da categoria é obrigatório.", "warning")
            return redirect(request.url)

         conn = get_db_connection()

             # Verifica duplicidade com nome em maiúsculas (garante comparação exata)
         existente = conn.execute(
            "SELECT 1 FROM CATEGORIA WHERE UPPER(TRIM(nome)) = ?", (nome,)
        ).fetchone()

         if existente:
            flash("Já existe um estabelecimento com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

         try:
            conn.execute("INSERT INTO CATEGORIA (nome) VALUES (?)", (nome,))
            conn.commit()
            flash("Categoria cadastrada com sucesso!", "success")
         except sqlite3.IntegrityError:
            flash("Erro ao cadastrar: nome já cadastrado.", "danger")
         finally:
            conn.close()

         return redirect(url_for('listar_categorias'))

    return render_template('editar_categoria.html', registro=None, tipo='categoria')

@app.route('/cadastro/categoria')
def consultar_categoria():
    conn = get_db_connection()
    try:
        categorias = conn.execute("SELECT * FROM CATEGORIA ORDER BY nome").fetchall()
    except Exception as e:
        categorias = []
        flash(f"Erro ao consultar categoria: {str(e)}", "danger")
    finally:
        conn.close()
    return render_template('consultar_categoria.html', categorias=categorias)

@app.route('/cadastro/categoria/editar/<int:id>', methods=['GET', 'POST'])
def editar_categoria(id):
    conn = get_db_connection()
    categoria = conn.execute("SELECT * FROM CATEGORIA WHERE id = ?", (id,)).fetchone()

    if not categoria:
        flash("Categoria não encontrada.", "danger")
        return redirect(url_for('listar_categorias'))

    if request.method == 'POST':
       novo_nome = request.form.get('nome', '').strip().upper()  # Nome em MAIÚSCULO

       if not novo_nome:
            flash("O nome da categoria é obrigatório.", "warning")
            return redirect(request.url)

        # Verifica se outro estabelecimento já usa esse nome
       duplicado = conn.execute(
            "SELECT 1 FROM CATEGORIA WHERE UPPER(TRIM(nome)) = ? AND id != ?", 
            (novo_nome, id)
        ).fetchone()

       if duplicado:
            flash("Já existe outro categoria com esse nome.", "danger")
            conn.close()
            return redirect(request.url) 

       conn.execute("UPDATE CATEGORIA SET nome = ? WHERE id = ?", (novo_nome, id))
       conn.commit()
       conn.close()
       flash("Categoria atualizada com sucesso!", "success")
       return redirect(url_for('listar_categorias'))

    conn.close()
    return render_template('editar_categoria.html', registro=categoria, tipo='categoria')

@app.route('/categorias')
def listar_categorias():
    conn = get_db_connection()
    categorias = conn.execute("SELECT * FROM CATEGORIA ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_categoria.html', categorias=categorias)

@app.route('/categoria/excluir/<int:id>', methods=['POST'])
def excluir_categoria(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM CATEGORIA WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Categoria excluída com sucesso!", "success")
    return redirect(url_for('listar_categorias'))




#--------------------------------Rotas do CRUD de local da compra------------------------

@app.route('/cadastro/local_compra/novo', methods=['GET', 'POST'])
def novo_local_compra():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip().upper()  # Normaliza e coloca em MAIÚSCULAS

        if not nome:
            flash("O nome do local da compra é obrigatório.", "warning")
            return redirect(request.url)

        conn = get_db_connection()

        # Verifica duplicidade com nome em maiúsculas (garante comparação exata)
        existente = conn.execute(
            "SELECT 1 FROM LOCAL_COMPRA WHERE UPPER(TRIM(nome)) = ?", (nome,)
        ).fetchone()

        if existente:
            flash("Já existe um local da compra com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        try:
            conn.execute("INSERT INTO LOCAL_COMPRA (nome) VALUES (?)", (nome,))
            conn.commit()
            flash("Local da compra cadastrada com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Erro ao cadastrar: nome já cadastrado.", "danger")
        finally:
            conn.close()
           
        return redirect(url_for('listar_local_compra'))
    
    return render_template('editar_local_compra.html', registro=None, tipo='local_compra')

@app.route('/cadastro/local_compra')
def consultar_local_compra():
    conn = get_db_connection()
    try:
        locais = conn.execute("SELECT * FROM LOCAL_COMPRA ORDER BY nome").fetchall()
    except Exception as e:
        locais = []
        flash(f"Erro ao consultar estabelecimentos: {str(e)}", "danger")
    finally:
        conn.close()
    return render_template('consultar_local_compra.html', local_compras=locais)

@app.route('/cadastro/local_compra/editar/<int:id>', methods=['GET', 'POST'])
def editar_local_compra(id):
    conn = get_db_connection()
    local_compra = conn.execute("SELECT * FROM LOCAL_COMPRA WHERE id = ?", (id,)).fetchone()

    if not local_compra:
        flash("Local da compra não encontrado.", "danger")
        return redirect(url_for('listar_local_compra'))
    
    if request.method == 'POST':
        novo_nome = request.form.get('nome', '').strip().upper()  # Nome em MAIÚSCULO

        if not novo_nome:
            flash("O nome do Local da compra é obrigatório.", "warning")
            return redirect(request.url)

        # Verifica se outro estabelecimento já usa esse nome
        duplicado = conn.execute(
            "SELECT 1 FROM LOCAL_COMPRA WHERE UPPER(TRIM(nome)) = ? AND id != ?", 
            (novo_nome, id)
        ).fetchone()

        if duplicado:
            flash("Já existe outro local da compra com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

    
        conn.execute("UPDATE LOCAL_COMPRA SET nome = ? WHERE id = ?", (novo_nome, id))
        conn.commit()
        conn.close()
        flash("local da Compra atualizado com sucesso!", "success")
        return redirect(url_for('listar_local_compra'))

    conn.close()
    return render_template('editar_local_compra.html', registro=local_compra, tipo='local_compra')

@app.route('/local_compras')
def listar_local_compra():
    conn = get_db_connection()
    local_compras = conn.execute("SELECT * FROM LOCAL_COMPRA ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_local_compra.html', local_compras=local_compras)

@app.route('/local_compra/excluir/<int:id>', methods=['POST'])
def excluir_local_compra(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM LOCAL_COMPRA WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Local da Compra excluído com sucesso!", "success")
    return redirect(url_for('listar_local_compra'))




#----------------------------Rotas do CRUD de produtos----------------------------------

@app.route('/cadastro/produto/novo', methods=['GET', 'POST'])
def novo_produto():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip().upper()  # Normaliza e coloca em MAIÚSCULAS
               
        if not nome:
            flash("O nome do produto é obrigatório.", "warning")
            return redirect(request.url)
          
        conn = get_db_connection()

 # Verifica duplicidade com nome em maiúsculas (garante comparação exata)
        existente = conn.execute(
            "SELECT 1 FROM PRODUTO WHERE UPPER(TRIM(nome)) = ?", (nome,)
        ).fetchone()

        if existente:
            flash("Já existe um produto esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        try:
            conn.execute("INSERT INTO PRODUTO (nome) VALUES (?)", (nome,))
            conn.commit()
            flash("Produto cadastrado com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Erro ao cadastrar: nome já cadastrado.", "danger")
        finally:
            conn.close()

        return redirect(url_for('listar_produtos'))
    
    return render_template('editar_produto.html', registro=None, tipo='produto')

@app.route('/cadastro/produto')
def consultar_produto():
    conn = get_db_connection()
    try:
       produtos = conn.execute("SELECT * FROM PRODUTO ORDER BY nome").fetchall()
    except Exception as e:
       produtos = []
       flash(f"Erro ao consultar estabelecimentos: {str(e)}", "danger")
    finally:
          conn.close()
    return render_template('consultar_produto.html', produtos=produtos)

@app.route('/cadastro/produto/editar/<int:id>', methods=['GET', 'POST'])
def editar_produto(id):
    conn = get_db_connection()
    produto = conn.execute("SELECT * FROM PRODUTO WHERE id = ?", (id,)).fetchone()

    if not produto:
        flash("Produto não encontrado.", "danger")
        return redirect(url_for('listar_produtos'))

    if request.method == 'POST':
        novo_nome = request.form.get('nome', '').strip().upper()  # Nome em MAIÚSCULO

        if not novo_nome:
            flash("O nome do produto é obrigatório.", "warning")
            return redirect(request.url)

        # Verifica se outro estabelecimento já usa esse nome
        duplicado = conn.execute(
            "SELECT 1 FROM PRODUTO WHERE UPPER(TRIM(nome)) = ? AND id != ?", 
            (novo_nome, id)
        ).fetchone()

        if duplicado:
            flash("Já existe outro produto com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        conn.execute("UPDATE PRODUTO SET nome = ? WHERE id = ?", (novo_nome, id))
        conn.commit()
        conn.close()
        flash("Produto atualizado com sucesso!", "success")
        return redirect(url_for('listar_produtos'))

    conn.close()
    return render_template('editar_produto.html', registro=produto, tipo='produto')

@app.route('/produtos')
def listar_produtos():
    conn = get_db_connection()
    produtos = conn.execute("SELECT * FROM PRODUTO ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_produto.html', produtos=produtos)

@app.route('/produto/excluir/<int:id>', methods=['POST'])
def excluir_produto(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM PRODUTO WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Produto excluído com sucesso!", "success")
    return redirect(url_for('listar_produtos'))




#-------------------------------Rotas do CRUD de bandeira ------------------------------

@app.route('/cadastro/bandeira/novo', methods=['GET', 'POST'])
def nova_bandeira():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip().upper()
        vencimento_dia = request.form['vencimento_dia']
        melhor_dia_compra = request.form['melhor_dia_compra']


        if not nome:
            flash("O nome da bandeira é obrigatória.", "warning")
            return redirect(request.url)

      
        conn = get_db_connection()

# Verifica duplicidade com nome em maiúsculas (garante comparação exata)
        existente = conn.execute(
            "SELECT 1 FROM BANDEIRA WHERE UPPER(TRIM(nome)) = ?", (nome,)
        ).fetchone()

        if existente:
            flash("Já existe uma bandeira com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        try:
            conn.execute("INSERT INTO BANDEIRA (nome, vencimento_dia, melhor_dia_compra) VALUES (?, ?, ?)", (nome, vencimento_dia, melhor_dia_compra))
            conn.commit()
            flash("Bandeira cadastrada com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Erro ao cadastrar: nome já cadastrado.", "danger")
        finally:
            conn.close()

        return redirect(url_for('listar_bandeiras'))
    
    return render_template('editar_bandeira.html', registro=None, tipo='bandeira')

@app.route('/cadastro/bandeira')
def consultar_bandeira():
    conn = get_db_connection()
    try:   
        bandeiras = conn.execute("SELECT * FROM BANDEIRA ORDER BY nome").fetchall()
    except Exception as e:
        bandeiras = []
        flash(f"Erro ao consultar Bandeiras: {str(e)}", "danger")
    finally:
       conn.close()
    return render_template('consultar_bandeira.html', bandeiras=bandeiras)

@app.route('/cadastro/bandeira/editar/<int:id>', methods=['GET', 'POST'])
def editar_bandeira(id):
    conn = get_db_connection()
    bandeira = conn.execute("SELECT * FROM bandeira WHERE id = ?", (id,)).fetchone()

    if not bandeira:
        flash("Bandeira não encontrada.", "danger")
        return redirect(url_for('listar_bandeiras'))

    if request.method == 'POST':
        novo_nome = request.form.get('nome', '').strip().upper()  # Nome em MAIÚSCULO
        novo_vencimento_dia = request.form.get('vencimento_dia')
        novo_melhor_dia_compra = request.form.get('melhor_dia_compra')

        if not (novo_nome and novo_vencimento_dia and novo_melhor_dia_compra):
            flash("Todos os campos devem ser preenchidos.", "warning")
            return redirect(request.url)
        
         # Verifica se outro estabelecimento já usa esse nome
        duplicado = conn.execute(
            "SELECT 1 FROM BANDEIRA WHERE UPPER(TRIM(nome)) = ? AND id != ?", 
            (novo_nome, id)
        ).fetchone()

        
        if duplicado:
            flash("Já existe outro bandeira com esse nome.", "danger")
            conn.close()
            return redirect(request.url)
        # Conversão segura para inteiros
        try:
            novo_vencimento_dia = int(novo_vencimento_dia)
            novo_melhor_dia_compra = int(novo_melhor_dia_compra)
        except ValueError:
            flash("Os campos de dias devem conter números válidos.", "danger")
            return redirect(request.url)

        conn.execute("""
            UPDATE bandeira
            SET nome = ?, vencimento_dia = ?, melhor_dia_compra = ?
            WHERE id = ?
        """, (novo_nome, novo_vencimento_dia, novo_melhor_dia_compra, id))

        conn.commit()
        conn.close()
        flash("Bandeira atualizada com sucesso!", "success")
        return redirect(url_for('listar_bandeiras'))

    conn.close()
    return render_template('editar_bandeira.html', registro=bandeira, tipo='bandeira')

@app.route('/bandeiras')
def listar_bandeiras():
    conn = get_db_connection()
    bandeiras = conn.execute("SELECT * FROM bandeira ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_bandeira.html', bandeiras=bandeiras)

@app.route('/bandeira/excluir/<int:id>', methods=['POST'])
def excluir_bandeira(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM bandeira WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("bandeira excluído com sucesso!", "success")
    return redirect(url_for('listar_bandeiras'))




#------------------------------Rotas do CRUD de forma de pagamento--------------------------------

@app.route('/cadastro/forma_pagamento/novo', methods=['GET', 'POST'])
def nova_forma_pagamento():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip().upper()  # Normaliza e coloca em MAIÚSCULAS
        
        if not nome:
            flash("O nome do forma de pagamento é obrigatório.", "warning")
            return redirect(request.url)
       
        conn = get_db_connection()

        # Verifica duplicidade com nome em maiúsculas (garante comparação exata)
        existente = conn.execute(
            "SELECT 1 FROM FORMA_PAGAMENTO WHERE UPPER(TRIM(nome)) = ?", (nome,)
        ).fetchone()

        if existente:
            flash("Já existe uma Forma de Pagamento com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        try:
            
            conn.execute("INSERT INTO FORMA_PAGAMENTO (nome) VALUES (?)", (nome,))
            conn.commit()
            flash("Forma de Pagamento cadastrada com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Erro ao cadastrar: nome já cadastrado.", "danger")
        finally:
            conn.close()


        return redirect(url_for('listar_formas_pagamento'))
    
    return render_template('editar_forma_pagamento.html', registro=None, tipo='forma de pagamento')

@app.route('/cadastro/forma_pagamento')
def consultar_forma_pagamento():
    conn = get_db_connection()
    try:
        forma_pagamento= conn.execute("SELECT * FROM FORMA_PAGAMENTO ORDER BY nome").fetchall()
    except Exception as e:
        forma_pagamento = []
        flash(f"Erro ao consultar forma de pagamento: {str(e)}", "danger")
    finally:
        conn.close()
    return render_template('consultar_forma_pagamento.html', forma_pagamento=forma_pagamento)

@app.route('/cadastro/forma_pagamento/editar/<int:id>', methods=['GET', 'POST'])
def editar_forma_pagamento(id):
    conn = get_db_connection()
    forma_pagamento= conn.execute("SELECT * FROM FORMA_PAGAMENTO WHERE id = ?", (id,)).fetchone()

    if not forma_pagamento:
        flash("forma de pagamento não encontrada.", "danger")
        return redirect(url_for('listar_formas_pagamento'))

    if request.method == 'POST':
        novo_nome = request.form.get('nome', '').strip().upper()  # Nome em MAIÚSCULO

        if not novo_nome:
            flash("A forma de pagamento é obrigatória.", "warning")
            return redirect(request.url)

        # Verifica se outro estabelecimento já usa esse nome
        duplicado = conn.execute(
            "SELECT 1 FROM FORMA_PAGAMENTO  WHERE UPPER(TRIM(nome)) = ? AND id != ?", 
            (novo_nome, id)
        ).fetchone()

        if duplicado:
            flash("Já existe outra forma de pagamento com esse nome.", "danger")
            conn.close()
            return redirect(request.url)
      
        conn.execute("UPDATE FORMA_PAGAMENTO SET nome = ? WHERE id = ?", (novo_nome, id))
        conn.commit()
        conn.close()
        flash("forma de pagamento atualizada com sucesso!", "success")
        return redirect(url_for('listar_formas_pagamento'))

    conn.close()
    return render_template('editar_forma_pagamento.html', registro=forma_pagamento, tipo='forma_pagamento')

@app.route('/formas_pagamento')
def listar_formas_pagamento():
    conn = get_db_connection()
    forma_pagamento= conn.execute("SELECT * FROM FORMA_PAGAMENTO ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_forma_pagamento.html', forma_pagamento=forma_pagamento)

@app.route('/forma_pagamento/excluir/<int:id>', methods=['POST'])
def excluir_forma_pagamento(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM FORMA_PAGAMENTO WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("forma de pagamento excluída com sucesso!", "success")
    return redirect(url_for('listar_formas_pagamento'))



#------------------------------- Rotas do CRUD de comprador ---------------------------------

@app.route('/cadastro/comprador/novo', methods=['GET', 'POST'])
def novo_comprador():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip().upper()  # Normaliza e coloca em MAIÚSCULAS
       
        if not nome:
            flash("O nome do comprador é obrigatório.", "warning")
            return redirect(request.url)
        
        conn = get_db_connection()

          # Verifica duplicidade com nome em maiúsculas (garante comparação exata)
        existente = conn.execute(
            "SELECT 1 FROM COMPRADOR WHERE UPPER(TRIM(nome)) = ?", (nome,)
        ).fetchone()
        
        if existente:
            flash("Já existe um comprador com esse nome.", "danger")
            conn.close()
            return redirect(request.url)

        try:
           conn.execute("INSERT INTO COMPRADOR (nome) VALUES (?)", (nome,))
           conn.commit()
           flash("Comprador cadastrado com sucesso!", "success")
        except sqlite3.IntegrityError:
            flash("Erro ao cadastrar: nome já cadastrado.", "danger")
        finally:
              conn.close()

        return redirect(url_for('listar_comprador'))
    
    return render_template('editar_comprador.html', registro=None, tipo='comprador')

@app.route('/cadastro/comprador')
def consultar_comprador():
    conn = get_db_connection()
    try:
        comprador = conn.execute("SELECT * FROM COMPRADOR ORDER BY nome").fetchall()
    except Exception as e:
        comprador = []
        flash(f"Erro ao consultar comprador: {str(e)}", "danger")
    finally:   
          conn.close()
    return render_template('consultar_comprador.html', comprador=comprador)

@app.route('/cadastro/comprador/editar/<int:id>', methods=['GET', 'POST'])
def editar_comprador(id):
    conn = get_db_connection()
    comprador = conn.execute("SELECT * FROM COMPRADOR WHERE id = ?", (id,)).fetchone()

    if not comprador:
        flash("Comprador não encontrado.", "danger")
        return redirect(url_for('listar_comprador'))

    if request.method == 'POST':
        novo_nome = request.form.get('nome', '').strip().upper()  # Nome em MAIÚSCULO
        if not novo_nome:
            flash("O nome do comprador é obrigatório.", "warning")
            return redirect(request.url)

        # Verifica se outro estabelecimento já usa esse nome
        duplicado = conn.execute(
            "SELECT 1 FROM COMPRADOR WHERE UPPER(TRIM(nome)) = ? AND id != ?", 
            (novo_nome, id)
        ).fetchone()

        if duplicado:
            flash("Já existe outro comprador com esse nome.", "danger")
            conn.close()
            return redirect(request.url)


        conn.execute("UPDATE COMPRADOR SET nome = ? WHERE id = ?", (novo_nome, id))
        conn.commit()
        conn.close()
        flash("Comprador atualizado com sucesso!", "success")
        return redirect(url_for('listar_comprador'))

    conn.close()
    return render_template('editar_comprador.html', registro=comprador, tipo='comprador')

@app.route('/comprador')
def listar_comprador():
    conn = get_db_connection()
    comprador = conn.execute("SELECT * FROM COMPRADOR ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_comprador.html', comprador=comprador)

@app.route('/comprador/excluir/<int:id>', methods=['POST'])
def excluir_comprador(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM COMPRADOR WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Comprador excluído com sucesso!", "success")
    return redirect(url_for('listar_comprador'))


#------------------------------- Rotas do CRUD de creditos ---------------------------------

@app.route('/cadastro/credito/novo', methods=['GET', 'POST'])
def novo_credito():
    if request.method == 'POST':
        data_do_credito = request.form['data_do_credito']
        valor_salario = request.form['valor_salario']

        if not data_do_credito or not valor_salario:
            flash('Data do crédito e valor são obrigatórios.', 'danger')
            return redirect(url_for('novo_credito'))

        try:
            valor = float(valor_salario.replace(',', '.'))
            # validação opcional da data
            datetime.strptime(data_do_credito, '%d/%m/%Y')

             # Aqui você NÃO converte para o formato ISO, salva como dd/mm/yyyy mesmo
            data_formatada = data_do_credito


        except ValueError:
            flash('Valor inválido ou data no formato incorreto.', 'danger')
            return redirect(url_for('novo_credito'))

        conn = get_db_connection()
        conn.execute(
            "INSERT INTO SALARIO_MES (DATA_DO_CREDITO, VALOR_SALARIO) VALUES (?, ?)",
            ( data_formatada, valor)
        )
        conn.commit()
        conn.close()
        flash('Crédito salarial inserido com sucesso!', 'success')
        return redirect(url_for('listar_credito'))

    return render_template('editar_credito.html',registro=None, tipo='Credito')

@app.route('/cadastro/credito')
def consultar_credito():
    conn = get_db_connection()
    try:
       creditos = conn.execute("SELECT * FROM SALARIO_MES ORDER BY DATA_DO_CREDITO DESC").fetchall()
    except Exception as e:
         creditos = []
         flash(f"Erro ao consultar comprador: {str(e)}", "danger")
    finally: 
          conn.close()
    return render_template('consultar_credito.html', creditos=creditos)

@app.route('/credito')
def listar_credito():
    conn = get_db_connection()
    creditos = conn.execute("SELECT * FROM SALARIO_MES ORDER BY DATA_DO_CREDITO DESC").fetchall()
    conn.close()
    return render_template('consultar_credito.html', creditos=creditos)

@app.route('/cadastro/credito/editar/<int:id>', methods=['GET', 'POST'])
def editar_credito(id):
    conn = get_db_connection()
    credito = conn.execute("SELECT * FROM SALARIO_MES WHERE id = ?", (id,)).fetchone()

    if not credito:
        flash("Credito não encontrado.", "danger")
        return redirect(url_for('listar_credito'))


    if request.method == 'POST':
        data_do_credito = request.form['data_do_credito']
        valor_salario = request.form['valor_salario']

        if not data_do_credito or not valor_salario:
            flash("Data do crédito e valor do crédito são obrigatórios.", "warning")
            conn.close()
            return redirect(request.url)

        # Verifica se há crédito duplicado (ajuste de nome de tabela e parâmetros!)
        duplicado = conn.execute(
            "SELECT 1 FROM SALARIO_MES WHERE DATA_DO_CREDITO = ? AND VALOR_SALARIO = ? AND id != ?", 
            (data_do_credito, valor_salario, id)
        ).fetchone()

        if duplicado:
            flash("Já existe outro crédito com esta data e valor.", "danger")
            conn.close()
            return redirect(request.url)

        # Atualização
        conn.execute(
            "UPDATE SALARIO_MES SET DATA_DO_CREDITO = ?, VALOR_SALARIO = ? WHERE id = ?",
            (data_do_credito, valor_salario, id)
        )
        conn.commit()
        conn.close()
        flash('Crédito salarial atualizado com sucesso!', 'success')
        return redirect(url_for('listar_credito'))

    conn.close()
    return render_template('editar_credito.html',registro=credito, tipo='credito')

@app.route('/cadastro/credito/excluir/<int:id>', methods=['POST'])
def excluir_credito(id):
    conn = get_db_connection()
    credito = conn.execute("SELECT * FROM SALARIO_MES WHERE id = ?", (id,)).fetchone()

    if credito is None:
        flash('Crédito não encontrado.', 'danger')
        conn.close()
        return redirect(url_for('consultar_credito'))

    conn.execute("DELETE FROM SALARIO_MES WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Crédito salarial excluído com sucesso!', 'success')
    return redirect(url_for('listar_credito'))



# --------------------Rotas para CRUD de Usuarios -----------------------------------
@app.route('/cadastro/usuarios', methods=['GET', 'POST'])
def cadastro_usuario():
    
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        senha = request.form.get('senha', '').strip()

        if not usuario or not senha:
            flash("Usuário e senha são obrigatórios.", "warning")
            return redirect(request.url)

        senha_hash = generate_password_hash(senha)

        conn = get_db_connection()

        existente = conn.execute("SELECT 1 FROM usuario WHERE usuario = ?", (usuario,)).fetchone()
        if existente:
            flash("Usuário já existe.", "danger")
            conn.close()
            return redirect(request.url)

        conn.execute("INSERT INTO usuario (usuario, senha_hash) VALUES (?, ?)", (usuario, senha_hash))
        conn.commit()
        conn.close()

        flash("Usuário cadastrado com sucesso!", "success")
        return redirect(url_for('login'))  # ou outra página
    print("Renderizando cadastro_usuario.html")
    return render_template('cadastro_usuario.html')

@app.route('/usuarios')
def consultar_usuario():
    conn = get_db_connection()
    usuarios = conn.execute("SELECT id, usuario FROM usuario ORDER BY usuario ASC").fetchall()
    conn.close()
    return render_template('consultar_usuarios.html', usuarios=usuarios)

@app.route('/usuarios', methods=['GET'])
def listar_usuarios():
    conn = get_db_connection()
    usuarios = conn.execute("SELECT id, usuario FROM usuario ORDER BY usuario ASC").fetchall()
    conn.close()
    return render_template('listar_usuarios.html', usuarios=usuarios)

@app.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
def editar_usuario(id):
    conn = get_db_connection()

    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        senha = request.form.get('senha', '').strip()

        if not usuario:
            flash("O nome de usuário é obrigatório.", "warning")
            return redirect(request.url)

        # Atualiza com ou sem nova senha
        if senha:
            senha_hash = generate_password_hash(senha)
            conn.execute(
                "UPDATE usuario SET usuario = ?, senha_hash = ? WHERE id = ?",
                (usuario, senha_hash, id)
            )
        else:
            conn.execute(
                "UPDATE usuario SET usuario = ? WHERE id = ?",
                (usuario, id)
            )

        conn.commit()
        conn.close()
        flash("Usuário atualizado com sucesso!", "success")
        return redirect(url_for('listar_usuarios'))

    # GET: carregar dados do usuário
    usuario = conn.execute("SELECT * FROM usuario WHERE id = ?", (id,)).fetchone()
    conn.close()

    if usuario is None:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for('listar_usuarios'))

    return render_template('editar_usuario.html', usuario=usuario)

@app.route('/usuarios/excluir/<int:id>', methods=['POST'])
def excluir_usuario(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM usuario WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Usuário excluído com sucesso!", "success")
    return redirect(url_for('listar_usuarios'))



#-------------------Rotas de acesso  ao ususarios do sistema  login e logout

@app.before_request
def verificar_login():
    rotas_livres = ['login', 'logout', 'static']
    if request.endpoint not in rotas_livres and 'user_id' not in session:
        flash('Você precisa estar logado para acessar esta página.', 'warning')
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario'].strip()
        senha = request.form['senha'].strip()

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM usuario WHERE usuario = ?", (usuario,)).fetchone()
        conn.close()

        if user and check_password_hash(user['senha_hash'], senha):
            session['user_id'] = user['usuario']
            print("Sessão após login:", dict(session))  # Debug: imprime sessão no console
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')

    print("Sessão ao exibir login GET:", dict(session))  # Debug para sessão no GET
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()  # limpa toda a sessão do usuário (remove login)
    flash('Você saiu do sistema com sucesso.', 'success')
    return redirect(url_for('login'))  # redireciona para a página de login



#------------------------ rotas complementares---------------------------------------- 




@app.route('/totais-despesas-mensais')
def totais_despesas_mensais():
    conn = get_db_connection()
    resultados = conn.execute("""
        SELECT 
            strftime('%m/%Y', P.data_vencimento) AS mes_ano,
            B.nome AS bandeira,
            P.pago,
            SUM(P.valor_parcela) AS total_parcela
        FROM PARCELAS P
        LEFT JOIN DESPESAS D ON P.despesa_id = D.id
        LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
        GROUP BY mes_ano, bandeira, pago
        ORDER BY mes_ano DESC
    """).fetchall()

    totais_nao_pagos = {}
    totais_pagos = {}
    bandeiras_set = set()
    
    for row in resultados:
        mes_ano = row['mes_ano']
        bandeira = row['bandeira']
        pago = row['pago']
        total = float(row['total_parcela'])
        bandeiras_set.add(bandeira)

        if pago == 0 or pago is None:  # não pagos
            if mes_ano not in totais_nao_pagos:
                totais_nao_pagos[mes_ano] = {}
            totais_nao_pagos[mes_ano][bandeira] = total
        else:  # pagos
            if mes_ano not in totais_pagos:
                totais_pagos[mes_ano] = {}
            totais_pagos[mes_ano][bandeira] = total

    # Ordenar os meses no formato MM/YYYY
    meses_ordenados = sorted(
        [m for m in set(list(totais_nao_pagos.keys()) + list(totais_pagos.keys())) if m is not None],
        key=lambda x: datetime.strptime(x, "%m/%Y"),
        reverse=True
    )
    
    conn.close()

    return render_template(
        'totais_despesas_mensais.html',
        totais_nao_pagos=totais_nao_pagos,
        totais_pagos=totais_pagos,
        meses=meses_ordenados,
        bandeiras=sorted(bandeiras_set)
    )


@app.route('/pagar', methods=['POST'])
def pagar():
    data = request.get_json()
    mes = data.get('mes')
    bandeira = data.get('bandeira')

    # Aqui você deve implementar a lógica para marcar as parcelas como pagas.
    # Como exemplo, vamos supor que há uma coluna 'pago' na tabela DESPESAS.
    # Você pode adaptar para a sua estrutura real.

    try:
        conn = get_db_connection()
        # Exemplo: Atualizar parcelas relacionadas ao mês e bandeira
        # Aqui você deve ajustar para sua lógica de pagamento
        conn.execute("""
            UPDATE PARCELAS
            SET pago = 1
            WHERE strftime('%m/%Y', data_vencimento) = ? AND despesa_id IN (
                SELECT D.id FROM DESPESAS D
                LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
                WHERE B.nome = ?
            )
        """, (mes, bandeira))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Erro ao marcar como pago: {e}")
        return jsonify({'success': False})


@app.route('/parcelas/<int:despesa_id>')
def listar_parcelas(despesa_id):
    conn = get_db_connection()

    # Buscar dados da despesa com os mesmos joins do consultar_despesas, só para o cabeçalho
    despesa = conn.execute("""
        SELECT
            D.id,
            P.nome AS produto,
            D.data_compra,
            B.nome AS bandeira,
            QP.quantidade AS qtd_parcelas
        FROM DESPESAS D
        LEFT JOIN PRODUTO P ON D.produto_id = P.id
        LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
        LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
        WHERE D.id = ?
    """, (despesa_id,)).fetchone()

    if despesa is None:
        conn.close()
        return jsonify({'error': 'Despesa não encontrada'}), 404

    # Buscar parcelas associadas (supondo tabela PARCELAS com despesa_id)
    parcelas = conn.execute("""
        SELECT data_vencimento, valor_parcela,pago
        FROM PARCELAS
        WHERE despesa_id = ?
        ORDER BY data_vencimento
    """, (despesa_id,)).fetchall()

    conn.close()

    # Montar o dict para JSON
    dados_despesa = {
        'id': despesa['id'],
        'produto': despesa['produto'],
        'data_compra': despesa['data_compra'],
        'bandeira': despesa['bandeira'],
        'qtd_parcelas': despesa['qtd_parcelas']
    }
    dados_parcelas = [
    {
        'data_vencimento': parcela['data_vencimento'],
        'valor': f"R$ {float(parcela['valor_parcela']):,.2f}".replace('.', ','),  # formato moeda BR
        'pago': parcela['pago']  # <-- aqui tem que ter vírgula, exceto se for o último item
    }
    for parcela in parcelas
]

    return jsonify({'despesa': dados_despesa, 'parcelas': dados_parcelas})

@app.route('/detalhes_comprador_mes', methods=['POST'])
def detalhes_comprador_mes():
    data = request.get_json()
    comprador_nome = data.get('comprador')
    mes_ano = data.get('mes')  # Exemplo: '07/2025'
    bandeira_nome = data.get('bandeira')  # Você pode usar se quiser filtrar bandeira depois

    # DEBUG
    print("Recebido comprador:", comprador_nome)
    print("Recebido mes_ano:", mes_ano)
    print("Recebido bandeira_nome:", bandeira_nome)

    if not comprador_nome or not mes_ano:
        return jsonify({'error': 'Parâmetros inválidos'}), 400

    try:
        datetime.strptime(mes_ano, "%m/%Y")
    except ValueError:
        return jsonify({'error': 'Formato de data inválido (esperado MM/YYYY)'}), 400

    conn = get_db_connection()

    # Query para pegar todas as parcelas do comprador, SEM filtrar o mês
    query = """
    SELECT 
        C.nome AS comprador,
        E.nome AS estabelecimento,
        D.data_compra,
        D.valor_compra,
        FP.nome AS forma_pagamento,
        B.nome AS bandeira,
        QP.quantidade AS quantidade_parcelas,
        P.data_vencimento,
        P.valor_parcela AS valor_parcela,
        P.pago,
        D.id AS despesa_id
    FROM PARCELAS P
    JOIN DESPESAS D ON P.despesa_id = D.id
    JOIN COMPRADOR C ON D.comprador_id = C.id
    LEFT JOIN ESTABELECIMENTO E ON D.estabelecimento_id = E.id
    LEFT JOIN FORMA_PAGAMENTO FP ON D.forma_pagamento_id = FP.id
    LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
    LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
    WHERE UPPER(C.nome) = UPPER(?)
    """

    despesas = conn.execute(query, [comprador_nome]).fetchall()
    conn.close()

    if not despesas:
        return jsonify({'error': 'Nenhuma despesa encontrada para esse comprador.'}), 404

    mes, ano = mes_ano.split('/')

    # Filtrar parcelas que vencem no mês/ano solicitado (substr da data no formato DD/MM/YYYY)
    parcelas_do_mes = [p for p in despesas if p["data_vencimento"][3:] == mes_ano]

    if not parcelas_do_mes:
        return jsonify({'error': 'Nenhuma parcela encontrada para esse comprador e mês.'}), 404

    from collections import defaultdict

    # Agrupa todas as parcelas da mesma despesa para calcular totais e quantas foram pagas
    parcelas_por_despesa = defaultdict(list)
    for p in despesas:
        parcelas_por_despesa[p["despesa_id"]].append(p)

    resultado = []

    for p in parcelas_do_mes:
        todas_parcelas = parcelas_por_despesa[p["despesa_id"]]
        todas_parcelas_ordenadas = sorted(todas_parcelas, key=lambda x: datetime.strptime(x["data_vencimento"], "%d/%m/%Y"))
        total_parcelas = len(todas_parcelas_ordenadas)
        parcelas_pagas = sum(1 for par in todas_parcelas_ordenadas if par["pago"])

        data_vencimento_atual = datetime.strptime(p["data_vencimento"], "%d/%m/%Y")
        parcela_atual = next(
           (i + 1 for i, par in enumerate(todas_parcelas_ordenadas)
           if datetime.strptime(par["data_vencimento"], "%d/%m/%Y") == data_vencimento_atual),
           None
        )

        if parcela_atual is None:
            parcela_atual = 1

        resultado.append({
            "comprador": p["comprador"],
            "estabelecimento": p["estabelecimento"],
            "data_compra": datetime.strptime(p["data_compra"], "%d/%m/%Y").strftime("%Y-%m-%d"),
            "valor_compra": parse_float_br(p["valor_compra"]),
            "quantidade_parcelas": total_parcelas,
            "forma_pagamento": p["forma_pagamento"],
            "bandeira": p["bandeira"],
            "valor_parcela_atual": float(p["valor_parcela"]),
            "data_vencimento": datetime.strptime(p["data_vencimento"], "%d/%m/%Y").strftime("%Y-%m-%d"),
            "pago": p["pago"],
            "parcelas": f"{parcela_atual}/{total_parcelas}",
            "parcelas_pagas": parcelas_pagas
        })

    # Total do mês - soma dos valores das parcelas do mês filtradas
    total_mes = sum(float(p["valor_parcela"]) for p in parcelas_do_mes)

    return jsonify({
        "comprador": comprador_nome,
        "total_mes": total_mes,
        "bandeira_nome": bandeira_nome,
        "detalhes": resultado
    })

@app.route('/detalhes_compras',methods=['GET', 'POST'], strict_slashes=False)
def detalhes_compras():

    if request.method == 'POST':
        data = request.get_json()
        bandeira = data.get('bandeira') if data else None
        mes_ano = data.get('mes_ano') if data else None
    else:
        bandeira = request.args.get('bandeira')
        mes_ano = request.args.get('mes_ano')

    # DEBUG
    print("Recebido bandeira:", bandeira)
    print("Recebido mes_ano:", mes_ano)

    if not bandeira or not mes_ano:
        return jsonify({'error': 'Parâmetros inválidos'}), 400

    try:
        datetime.strptime(mes_ano, "%m/%Y")
    except ValueError:
        return jsonify({'error': 'Formato de data inválido (esperado MM/YYYY)'}), 400
    
    try:
         mes, ano = mes_ano.split('/')
    except ValueError:
        return jsonify({'error': 'Formato de data inválido (esperado MM/YYYY)'}), 400
    

    conn = get_db_connection()
    try:
      
      query = """
      SELECT 
         E.nome AS estabelecimento,
         D.data_compra,
         D.valor_compra,
         FP.nome AS forma_pagamento,
         B.nome AS bandeira,
         QP.quantidade AS quantidade_parcelas,
         P.data_vencimento,
         P.valor_parcela AS valor_parcela,
         P.pago
      FROM PARCELAS P
      JOIN DESPESAS D ON P.despesa_id = D.id
      LEFT JOIN ESTABELECIMENTO E ON D.estabelecimento_id = E.id
      LEFT JOIN FORMA_PAGAMENTO FP ON D.forma_pagamento_id = FP.id
      LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
      LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
      WHERE UPPER(B.nome) LIKE UPPER(?) || '%'
      AND substr(P.data_vencimento, 4, 7) = ?
      ORDER BY 
         substr(D.data_compra, 7, 4) || '-' || substr(D.data_compra, 4, 2) || '-' || substr(D.data_compra, 1, 2)
      """
# Ajusta o parâmetro bandeira para só o texto principal, sem o "- 6"
      bandeira_principal = bandeira.split(' - ')[0]  # Pega só 'TORRA TORRA'

# Ajusta a bandeira para ignorar o sufixo " - 6" 

      print("Bandeira principal usada na query:", bandeira_principal)

      despesas = conn.execute(query, [bandeira_principal, mes_ano]).fetchall()


     #despesas = conn.execute(query, [bandeira, mes_ano]).fetchall()
      print(f"Despesas encontradas para bandeira {bandeira}: {len(despesas)}")
 
    finally:
      conn.close()

    if not despesas:
        return jsonify({'error': 'Nenhuma despesa encontrada para essa bandeira e mês.'}), 404

    total_mes = sum(float(d["valor_parcela"]) for d in despesas if d["valor_parcela"])
    quantidade_parcelas = sum(d["quantidade_parcelas"] or 0 for d in despesas)

    resultado = []
    for d in despesas:
        try:
           data_vencimento_iso = datetime.strptime(d["data_vencimento"], "%d/%m/%Y").strftime("%Y-%m-%d")
           data_compra_iso = datetime.strptime(d["data_compra"], "%d/%m/%Y").strftime("%Y-%m-%d")
        except Exception as e:
           print(f"Erro ao converter datas:{e}")
           data_vencimento_iso =d["data_vencimento"]
           data_compra_iso =d["data_compra"]

        valor_raw = d["valor_compra"]
        if isinstance(valor_raw, str):
            valor_compra = float(valor_raw.replace(',', '.'))
        else:
            valor_compra = float(valor_raw)


        resultado.append({
            "estabelecimento": d["estabelecimento"],
            "data_compra": data_compra_iso,
            "valor_compra":valor_compra,
            "quantidade_parcelas": d["quantidade_parcelas"],
            "forma_pagamento": d["forma_pagamento"],
            "bandeira": d["bandeira"],
            "valor_parcela_atual": float(d["valor_parcela"]),
            "data_vencimento": data_vencimento_iso,
            "pago": d["pago"]
        })

    return jsonify({
        "bandeira": bandeira,
        "total_mes": total_mes,
        "quantidade_parcelas": quantidade_parcelas,
        "detalhes": resultado
    })



@app.route('/export_csv', methods=['GET'])
def export_csv():
    conn = get_db_connection()

    # Filtros de período (para exportação)
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    categoria_id = request.args.get('categoria_id')

    # Base da consulta
    query = """
        SELECT 
            D.data_compra,
            P.nome AS produto_nome,
            D.valor_parcela,
            D.quantidade_parcelas,
            C.nome AS comprador_nome,
            FP.nome AS forma_pagamento,
            B.nome AS bandeira_nome
            QP.quantidade AS quantidade_parcelas
        FROM DESPESAS D
        LEFT JOIN PRODUTO P ON D.produto_id = P.id
        LEFT JOIN COMPRADOR C ON D.comprador_id = C.id
        LEFT JOIN FORMA_PAGAMENTO FP ON D.forma_pagamento_id = FP.id
        LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
        LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
         WHERE 1=1
    """

    if data_inicio:
        query += f" AND D.data_compra >= '{data_inicio}'"
    if data_fim:
        query += f" AND D.data_compra <= '{data_fim}'"
    if categoria_id:
        query += f" AND D.categoria_id = {categoria_id}"

    # Executar consulta
    despesas = conn.execute(query).fetchall()
    conn.close()

    # Criar o CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Escrever cabeçalho
    writer.writerow(['Data Compra', 'Produto', 'Valor Parcela', 'Quantidade Parcelas', 'Comprador', 'Forma Pagamento', 'Bandeira'])

    # Escrever os dados das despesas
    for despesa in despesas:
        writer.writerow([
            despesa['data_compra'],
            despesa['produto_nome'],
            despesa['valor_parcela'],
            despesa['quantidade_parcelas'],
            despesa['comprador_nome'],
            despesa['forma_pagamento'],
            despesa['bandeira_nome']
        ])

    # Preparar a resposta
    output.seek(0)
    return Response(output, 
                    mimetype='text/csv', 
                    headers={"Content-Disposition": "attachment;filename=despesas.csv"})



#---------------------------- Rotas para o Menu  Combustiveis ----------------------------



@app.route('/outros/combustivel', methods=['GET', 'POST'])
def combustivel():
    conn = get_db_connection()
    cursor = conn.cursor()


    # Filtros de mês/ano
    mes = request.args.get('mes') or datetime.today().strftime('%m')
    ano = request.args.get('ano') or datetime.today().strftime('%Y')

    dados = obter_dados_por_mes(ano, mes)

    total_quantidade = sum(row['quantidade'] for row in dados)
    total_km = sum(row['kilometragem'] for row in dados)
    total_pago = sum(row['valor_pago'] for row in dados)

    media_consumo = round(sum(row['consumo'] for row in dados) / len(dados), 2) if dados else 0

    # Totais do ano
    cursor.execute('''
    SELECT 
        SUM(quantidade),
        SUM(kilometragem),
        SUM(valor_pago)
    FROM combustivel
    WHERE data_abastecimento LIKE ? 
    ''', (f'%/{ano}',))
    total_ano = cursor.fetchone()
    conn.close()

    return render_template('combustivel.html',
                           dados=dados,
                           mes=mes,
                           ano=ano,
                           total_quantidade=total_quantidade,
                           total_km=total_km,
                           total_pago=total_pago,
                           media_consumo=media_consumo,
                           total_ano=total_ano)

@app.route('/grafico/consumo')
def grafico_consumo():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT data_abastecimento, consumo FROM combustivel ORDER BY data_abastecimento DESC')
    rows = cursor.fetchall()
    conn.close()

    dados_por_mes = defaultdict(list)
    for data, consumo in rows:
        # Extrair mês/ano corretamente
        try:
           # mes_ano = data[5:7] + '/' + data[:4]  # MM/YYYY
           mes_ano = datetime.strptime(data, '%d/%m/%Y').strftime('%m/%Y')
        except:
            continue  # ignora registros com data malformada

        dados_por_mes[mes_ano].append(consumo)

    labels = []
    valores = []

    for mes in sorted(dados_por_mes.keys()):
        media = round(sum(dados_por_mes[mes]) / len(dados_por_mes[mes]), 2)
        labels.append(mes)
        valores.append(media)

    return jsonify({'labels': labels, 'valores': valores})

@app.route('/incluir_abastecimento', methods=['GET', 'POST'])
def incluir_abastecimento():
   
     conn = get_db_connection()
     cursor = conn.cursor()
       
     if request.method == 'POST':
          data = converter_para_ddmmYYYY(request.form['data_abastecimento'])
          quantidade = round(float(request.form['quantidade']), 3)
          km = round(float(request.form['kilometragem']), 2)
          preco = round(float(request.form['preco_litro']), 2)

          valor_pago = round(quantidade * preco, 2)
          consumo = round(km / quantidade, 3) if quantidade != 0 else 0

          cursor.execute('''
            INSERT INTO combustivel (
                data_abastecimento, quantidade, kilometragem, preco_litro, valor_pago, consumo
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (data, quantidade, km, preco, valor_pago, consumo))
          conn.commit()
          flash('Abastecimento adicionado com sucesso!', 'success')
          return redirect(url_for('combustivel'))
             
     return render_template('incluir_abastecimento.html')

@app.route('/outros/combustivel/consultar')
def consultar_combustivel():
    destaque = request.args.get('destaque', type=int)
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM combustivel
        ORDER BY date(substr(data_abastecimento, 7, 4) || '-' || 
                      substr(data_abastecimento, 4, 2) || '-' || 
                      substr(data_abastecimento, 1, 2)) ASC
    ''')
    registros = cursor.fetchall()
    conn.close()


    registros = [dict(r) for r in registros]
    for r in registros:
        r['data_abastecimento'] = converter_para_ddmmYYYY(r['data_abastecimento'])


    return render_template('consultar_combustivel.html', registros=registros, destaque=destaque)

@app.route('/outros/combustivel/editar/<int:id>', methods=['GET', 'POST'])
def editar_combustivel(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        data = converter_para_ddmmYYYY(request.form['data_abastecimento'])
        quantidade = float(request.form['quantidade'])
        km = float(request.form['kilometragem'])
        preco = float(request.form['preco_litro'])

        valor_pago = calcular_valor_pago(quantidade, preco)
        consumo = calcular_consumo(km, quantidade)

        cursor.execute('''
            UPDATE combustivel
            SET data_abastecimento=?, quantidade=?, kilometragem=?, preco_litro=?, valor_pago=?, consumo=?
            WHERE id=?
        ''', (data, quantidade, km, preco, valor_pago, consumo, id))
        conn.commit()
        conn.close()
        return redirect(url_for('consultar_combustivel', destaque=id))

    cursor.execute('SELECT * FROM combustivel WHERE id=?', (id,))
    row = cursor.fetchone()
    conn.close()
    row = dict(row)
    row['data_abastecimento'] = converter_para_ddmmYYYY(row['data_abastecimento'])


    return render_template('editar_combustivel.html', row=row)

@app.route('/outros/combustivel/deletar/<int:id>')
def deletar_combustivel(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM combustivel WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('combustivel'))



@app.route('/exportar/csv')
def exportar_csv():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM combustivel')
    rows = cursor.fetchall()
    conn.close()

    # Cabeçalhos do CSV
    header = ['ID', 'Data Abastecimento', 'Quantidade', 'Kilometragem', 'Preço por Litro', 'Valor Pago', 'Consumo']

    # Monta o conteúdo do CSV
    def generate():
        yield ','.join(header) + '\n'
        for row in rows:
            data_formatada = converter_para_ddmmYYYY(row['data_abastecimento'])
            line = f"{row['id']},{row['data_abastecimento']},{row['quantidade']},{row['kilometragem']},{row['preco_litro']},{row['valor_pago']},{row['consumo']}\n"
            yield line

    return Response(generate(), mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=combustivel.csv"})

@app.route('/exportar/pdf')
def exportar_pdf():
    mes = request.args.get('mes') or datetime.today().strftime('%m')
    ano = request.args.get('ano') or datetime.today().strftime('%Y')
    dados = obter_dados_por_mes(ano, mes)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=4*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    story = []

    # Tabela de dados com separadores
    table_data = [['Data', 'Qtd (L)', 'Km Rodados', 'Preço/L', 'Valor Pago']]
    total_qtd = total_km = total_pago = 0

    for row in dados:
        data_formatada = converter_para_ddmmYYYY(row['data_abastecimento'])
        table_data.append([
            row['data_abastecimento'],
            f"{row['quantidade']:.3f}",
            f"{row['kilometragem']:.2f}",
            f"{row['preco_litro']:.2f}",
            f"{row['valor_pago']:.2f}"
        ])
        total_qtd += row['quantidade']
        total_km += row['kilometragem']
        total_pago += row['valor_pago']

    # Linha de totais
    table_data.append([
        'Totais',
        f"{total_qtd:.3f}",
        f"{total_km:.2f}",
        '',
        f"{total_pago:.2f}"
    ])

    table = Table(table_data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (1,1), (-1,-2), 'RIGHT'),
        ('ALIGN', (1,-1), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.whitesmoke),
    ]))

    story.append(table)
    story.append(Spacer(1, 12))

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)

    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=relatorio_{ano}_{mes}.pdf'
    return response



if __name__ == '__main__':
    app.secret_key = 'segredo-super-seguro'
    app.run(debug=True)
