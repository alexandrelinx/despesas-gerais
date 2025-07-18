from db import inicializar_banco
inicializar_banco()

from flask import Flask, render_template, request, redirect, url_for, flash
import os
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta
import locale
from datetime import datetime, timedelta
import calendar
from flask import session, redirect, url_for, flash
from flask import request, redirect, url_for, flash, render_template
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask import render_template
from collections import defaultdict
from util.helpers import calcular_parcelas 
from util.helpers import calcular_totais_por_mes
from flask_wtf.csrf import CSRFProtect
from flask import request, jsonify
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask_wtf.csrf import CSRFError



app = Flask(__name__)
app.config['SECRET_KEY'] = 'despesas'  
csrf = CSRFProtect(app)


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('Erro de segurança: token CSRF inválido ou expirado. Recarregue a página e tente novamente.', 'danger')
    return redirect(request.url)

#DB = 'despesas.db'

DB_PATH = os.path.join(os.path.dirname(__file__), 'banco', 'despesas.db')
# Função para conexão com o banco de dados
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def real(value):
    """Formata um número float como moeda brasileira"""
    try:
        return f"R$ {float(value):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return value

app.jinja_env.filters['real'] = real

# Configuração de localidade para exibir datas em português
try:
     locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')  # Linux/Mac
except:
     locale.setlocale(locale.LC_TIME, 'Portuguese_Brazil.1252')


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

@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cursor = conn.cursor()

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
        E.nome AS estabelecimento
    FROM DESPESAS D
    LEFT JOIN ESTABELECIMENTO E ON D.estabelecimento_id = E.id                        
    LEFT JOIN PRODUTO PRD ON D.produto_id = PRD.id
    LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
    LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
    ORDER BY D.data_compra DESC
    """).fetchall()

    despesas = [dict(row) for row in despesas]

    parcelas_por_mes = defaultdict(lambda: defaultdict(float))
    parcelas_status_pagamento = defaultdict(lambda: defaultdict(list))
    meses_set = set()
    parcelas_exibidas = []

    for despesa in despesas:
        valor_parcela = float(despesa['valor_parcela_despesa'])

        parcelas_no_banco = conn.execute("""
            SELECT id, data_vencimento, pago
            FROM parcelas 
            WHERE despesa_id = ?
            ORDER BY data_vencimento
        """, (despesa['despesa_id'],)).fetchall()

        for idx, parcela in enumerate(parcelas_no_banco, start=1):
            vencimento_str = parcela['data_vencimento']  # Ex: '15/06/2025'
            dt_vencimento = datetime.strptime(vencimento_str, "%d/%m/%Y")
            mes_ano = dt_vencimento.strftime("%m/%Y")
            meses_set.add(mes_ano)

            pago_parcela = int(parcela['pago'] or 0)
            chave_bandeira = f"{despesa['bandeira_nome']} - {despesa['vencimento_bandeira']}"

            parcelas_por_mes[chave_bandeira][mes_ano] += valor_parcela
            parcelas_status_pagamento[chave_bandeira][mes_ano].append(pago_parcela)

            parcelas_exibidas.append({
                "id": despesa['despesa_id'],
                "numero_parcela": idx,
                "total_parcelas": despesa['quantidade_parcelas'],
                "data_vencimento": dt_vencimento,
                "valor_parcela": valor_parcela,
                "parcela_alterada": bool(despesa.get("parcela_alterada", 0)),
                "produto_nome": despesa['produto_nome'],
                "bandeira_nome": despesa['bandeira_nome'],
                "estabelecimento": despesa['estabelecimento'],
                "data_compra": despesa['data_compra'],
                "pago": pago_parcela
            })

    pagamento_por_mes_bandeira = {}
    for bandeira, meses in parcelas_status_pagamento.items():
        pagamento_por_mes_bandeira[bandeira] = {}
        for mes, lista_pagamentos in meses.items():
            status_normalizado = [bool(p) for p in lista_pagamentos]
            pagamento_por_mes_bandeira[bandeira][mes] = all(status_normalizado)
            print(f"{bandeira} | {mes} => Original: {lista_pagamentos}, Normalizado: {status_normalizado}")

    colunas_meses = sorted(meses_set, key=lambda x: datetime.strptime(x, "%m/%Y"))
    totais_por_mes, total_geral = calcular_totais_por_mes(parcelas_por_mes, colunas_meses)

    conn.close()

    csrf_token = generate_csrf()

    return render_template(
        'dashboard.html',
        parcelas=parcelas_exibidas,
        parcelas_por_mes=parcelas_por_mes,
        colunas_meses=colunas_meses,
        totais_por_mes=totais_por_mes,
        total_geral=total_geral,
        pagamento_por_mes_bandeira=pagamento_por_mes_bandeira,
        csrf_token=csrf_token
    )


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
            data_compra = request.form['data_compra']  # formato: yyyy-mm-dd
            quantidade_parcelas = int(conn.execute(
                "SELECT quantidade FROM QUANTIDADE_PARCELAS WHERE id = ?", 
                (request.form['quantidade_parcelas_id'],)
            ).fetchone()['quantidade'])

            bandeira_id = request.form['bandeira_id']
            bandeira_dados = conn.execute(
                "SELECT melhor_dia_compra, vencimento_dia FROM BANDEIRA WHERE id = ?",
                (bandeira_id,)
            ).fetchone()

            melhor_dia_compra = bandeira_dados['melhor_dia_compra']
            vencimento_bandeira = bandeira_dados['vencimento_dia']

            # Converter a data de compra (YYYY-MM-DD)
            data_compra_dt = datetime.strptime(data_compra, "%d/%m/%Y")

            # Define a data da primeira parcela com base no melhor dia de compra
            if data_compra_dt.day < melhor_dia_compra:
                primeira_data = data_compra_dt.replace(day=1) + relativedelta(months=1)
            else:
                primeira_data = data_compra_dt.replace(day=1) + relativedelta(months=2)

            # Ajusta para o vencimento da fatura
            try:
                primeira_data = primeira_data.replace(day=vencimento_bandeira)
            except ValueError:
                ultima_do_mes = (primeira_data + relativedelta(months=1, day=1)) - relativedelta(days=1)
                primeira_data = ultima_do_mes

            # Gera as datas das parcelas
            parcelas = [primeira_data + relativedelta(months=i) for i in range(quantidade_parcelas)]

            # Inserir parcelas
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
                           quantidades=quantidade_parcelas)

@app.route('/consultar_despesas', methods=['GET', 'POST'])
def consultar_despesas():
    conn = get_db_connection()

    # Filtros da URL
    bandeira_filtro = request.args.get('bandeira', '').strip()
    data_inicio = request.args.get('data_inicio', '').strip()
    data_fim = request.args.get('data_fim', '').strip()

    # Buscar todas as bandeiras para popular o filtro
    bandeiras = conn.execute("SELECT id, nome FROM BANDEIRA").fetchall()

    # Monta a query base
    query = """
        SELECT
            D.id,
            E.nome  AS estabelecimento,
            P.nome AS produto_nome,
            D.valor_compra,
            D.data_compra,
            FP.nome AS forma_pagamento,
            B.nome AS bandeira_nome,
            PQP.tipo AS parcelamento_tipo,
            D.valor_parcela,
            D.observacao, 
            D.parcela_alterada
           
        FROM DESPESAS D
        LEFT JOIN PRODUTO P ON D.produto_id = P.id
        LEFT JOIN FORMA_PAGAMENTO FP ON D.forma_pagamento_id = FP.id
        LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
        LEFT JOIN ESTABELECIMENTO E ON D.estabelecimento_id = E.id
        LEFT JOIN PARCELAMENTO PQP ON D.parcelamento_id = PQP.id
        WHERE 1=1
    """

    params = []

    # Filtro por bandeira
    if bandeira_filtro:
        query += " AND B.id = ?"
        params.append(bandeira_filtro)

    # Filtro por data (formato dd/mm/yyyy como string)
    if data_inicio:
        query += """
            AND (
                substr(D.data_compra, 7, 4) || substr(D.data_compra, 4, 2) || substr(D.data_compra, 1, 2)
            ) >= ?
        """
        params.append(data_inicio.replace("-", ""))  # yyyy-mm-dd → yyyymmdd

    if data_fim:
        query += """
            AND (
                substr(D.data_compra, 7, 4) || substr(D.data_compra, 4, 2) || substr(D.data_compra, 1, 2)
            ) <= ?
        """
        params.append(data_fim.replace("-", ""))

    # Ordenação decrescente por data
    query += """
        ORDER BY substr(D.data_compra, 7, 4) || substr(D.data_compra, 4, 2) || substr(D.data_compra, 1, 2) DESC
    """

    # Debug
    print("Query SQL:", query)
    print("Parâmetros:", params)

    # Executa a consulta
    despesas = conn.execute(query, params).fetchall()
    conn.close()

    # Renderiza o template
    return render_template(
        'consultar_despesas.html',
        despesas=despesas,
        bandeiras=bandeiras,
        bandeira_selecionada=bandeira_filtro
    )

@app.route('/editar_despesa/<int:id>', methods=['GET', 'POST'])
def editar_despesa(id):
    conn = get_db_connection()
    despesa = conn.execute("SELECT * FROM DESPESAS WHERE id = ?", (id,)).fetchone()

    if not despesa:
        flash("Despesa não encontrada!", "danger")
        return redirect(url_for('consultar_despesas'))

    if request.method == 'POST':
        print("valor_parcela do form:", request.form.get('valor_parcela'))
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
            parcela_alterada = 1
            print(f"parcela_alterada definida para: {parcela_alterada}")

            conn.execute("""
                UPDATE DESPESAS
                SET estabelecimento_id = ?, categoria_id = ?, local_compra_id = ?, comprador_id = ?,
                    produto_id = ?, data_compra = ?, valor_compra = ?, forma_pagamento_id = ?, bandeira_id = ?,
                    parcelamento_id = ?, quantidade_parcelas_id = ?, valor_parcela = ?, observacao = ?, parcela_alterada = ?
                WHERE id = ?
            """, (*dados, parcela_alterada, id))

            conn.commit()
            print("Despesa atualizada com sucesso, ID:", id)

            # Atualização das parcelas
            nova_qtd_parcelas = int(conn.execute(
                "SELECT quantidade FROM QUANTIDADE_PARCELAS WHERE id = ?",
                (request.form['quantidade_parcelas_id'],)
            ).fetchone()['quantidade'])

            bandeira_id = request.form['bandeira_id']

            bandeira_dados = conn.execute(
                "SELECT nome, melhor_dia_compra, vencimento_dia FROM BANDEIRA WHERE id = ?",
                (bandeira_id,)
            ).fetchone()

            nome_bandeira = bandeira_dados['nome']
            melhor_dia_compra = bandeira_dados['melhor_dia_compra']
            vencimento_dia = bandeira_dados['vencimento_dia']
            nova_data_compra = datetime.strptime(request.form['data_compra'], "%d/%m/%Y")
            novo_valor_parcela = float(request.form['valor_parcela'])

            if "neon" in nome_bandeira.lower():
                # Regra especial da bandeira Neon
                if nova_data_compra.day >= melhor_dia_compra:
                    primeiro_mes = nova_data_compra + relativedelta(months=1)
                else:
                    primeiro_mes = nova_data_compra 
            else:
                # Regra padrão (das outras bandeiras)
                if nova_data_compra.day < melhor_dia_compra:
                    primeiro_mes = nova_data_compra + relativedelta(months=1)
                else:
                    primeiro_mes = nova_data_compra + relativedelta(months=2)

            try:
                primeira_data = primeiro_mes.replace(day=vencimento_dia)
            except ValueError:
                primeira_data = (primeiro_mes + relativedelta(months=1, day=1)) - relativedelta(days=1)

            datas_novas = [primeira_data + relativedelta(months=i) for i in range(nova_qtd_parcelas)]

            print("📌 Datas novas calculadas para as parcelas:")
            for i, d in enumerate(datas_novas, start=1):
                print(f"  Parcela {i}: {d.strftime('%d/%m/%Y')}")

            parcelas_existentes = conn.execute(
                "SELECT * FROM PARCELAS WHERE despesa_id = ? ORDER BY numero_parcela", (id,)
            ).fetchall()
            qtd_parcelas_atual = len(parcelas_existentes)

            if nova_qtd_parcelas > qtd_parcelas_atual:
                for i in range(qtd_parcelas_atual, nova_qtd_parcelas):
                    conn.execute("""
                        INSERT INTO PARCELAS (despesa_id, data_vencimento, valor_parcela, numero_parcela)
                        VALUES (?, ?, ?, ?)
                    """, (id, datas_novas[i].strftime("%d/%m/%Y"), novo_valor_parcela, i + 1))

            elif nova_qtd_parcelas < qtd_parcelas_atual:
                for i in range(nova_qtd_parcelas, qtd_parcelas_atual):
                    conn.execute("""
                        DELETE FROM PARCELAS WHERE despesa_id = ? AND numero_parcela = ?
                    """, (id, i + 1))

            for i, parcela in enumerate(parcelas_existentes[:nova_qtd_parcelas]):
                print(f"🛠 Atualizando parcela ID {parcela['id']} -> nova data: {datas_novas[i].strftime('%d/%m/%Y')} | valor: {novo_valor_parcela}")
                conn.execute("""
                    UPDATE PARCELAS
                    SET data_vencimento = ?, valor_parcela = ?
                    WHERE id = ?
                """, (datas_novas[i].strftime("%d/%m/%Y"), novo_valor_parcela, parcela['id']))

            conn.commit()
            flash("Despesa atualizada com sucesso!", "success")
            print("✅ Commit realizado com sucesso. Parcelas atualizadas no banco.")
            return redirect(url_for('consultar_despesas'))

        except Exception as e:
            conn.rollback()
            print("Erro ao atualizar despesa:", e)
            flash(f"Erro ao atualizar despesa: {e}", "danger")
            print("Erro:", e)

    # Carrega dados para GET
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


# Rotas do CRUD de estabelecimento

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





#Rotas do CRUD de Categoria 

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





#Rotas do CRUD de local da compra

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





#Rotas do CRUD de produtos

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





#Rotas do CRUD de bandeira

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





#Rotas do CRUD de forma de pagamento

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





# Rotas do CRUD de comprador

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

#from flask import jsonify

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


# Função para exportar os dados de despesas para CSV
import csv
from io import StringIO
from flask import Response

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


#Rotas para login e logout

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





if __name__ == '__main__':
    app.secret_key = 'segredo-super-seguro'
    app.run(debug=True)
