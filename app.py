from db import inicializar_banco
inicializar_banco()

from flask import Flask, render_template, request, redirect, url_for, flash
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
app = Flask(__name__)
DB = 'despesas.db'

# Função para conexão com o banco de dados
def get_db_connection():
    conn = sqlite3.connect(DB)
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

# Função para calcular as parcelas com base na data da compra e vencimento
def calcular_parcelas(data_compra, quantidade_parcelas, vencimento_bandeira):
    try:
        data_compra = datetime.strptime(data_compra, "%d/%m/%Y")
    except Exception as e:
        print(f"Erro ao converter data: {data_compra} -> {e}")
        return []

    parcelas = []

    # Define a data da primeira parcela com base no vencimento
    if data_compra.day < vencimento_bandeira:
        primeira_parcela = data_compra.replace(day=1) + relativedelta(months=1)
    else:
        primeira_parcela = data_compra.replace(day=1) + relativedelta(months=2)

    # Garante que o dia do vencimento seja possível (ex: não existe 31 em todos os meses)
    try:
        primeira_parcela = primeira_parcela.replace(day=vencimento_bandeira)
    except ValueError:
        # Se o dia não existe no mês, pega o último dia do mês
        ultima_do_mes = (primeira_parcela + relativedelta(months=1, day=1)) - relativedelta(days=1)
        primeira_parcela = ultima_do_mes

    # Gera as parcelas
    for i in range(quantidade_parcelas):
        vencimento = primeira_parcela + relativedelta(months=i)
        parcelas.append(vencimento)

    return parcelas



from flask import render_template
from datetime import datetime
from dateutil.relativedelta import relativedelta


from datetime import datetime
from collections import defaultdict

from datetime import datetime


@app.route('/')
def dashboard():
    conn = get_db_connection()

    # Consulta para obter as parcelas com os dados necessários
    parcelas = conn.execute("""
       SELECT 
        P.id AS parcela_id,
        P.numero_parcela,
        P.data_vencimento,
        P.valor_parcela,
        D.data_compra,
        D.valor_compra,
        D.valor_parcela AS valor_parcela_despesa,
        QP.quantidade AS quantidade_parcelas,
        PRD.nome AS produto_nome,
        B.nome AS bandeira_nome,
        B.vencimento_dia AS vencimento_bandeira,
        B.melhor_dia_compra AS melhor_dia_compra,
        E.nome  AS estabelecimento  -- Campo 'estabelecimento' adicionado
    FROM PARCELAS P
    LEFT JOIN DESPESAS D ON P.despesa_id = D.id
    LEFT JOIN ESTABELECIMENTO E ON D.estabelecimento_id = E.id                        
    LEFT JOIN PRODUTO PRD ON D.produto_id = PRD.id
    LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
    LEFT JOIN QUANTIDADE_PARCELAS QP ON D.quantidade_parcelas_id = QP.id
    
    ORDER BY  D.data_compra DESC
    """)

    # Converte para uma lista de dicionários
    parcelas = [dict(row) for row in parcelas]

    # Convertendo a data_vencimento para datetime, caso seja uma string
    for p in parcelas:
        if isinstance(p['data_vencimento'], str):
            try:
                # Convertendo a data para o formato correto ('dd/mm/yyyy')
                p['data_vencimento'] = datetime.strptime(p['data_vencimento'], '%d/%m/%Y')
            except ValueError as e:
                print(f"Erro na conversão da data: {e}")

    # Agrupamento por bandeira/mês
    parcelas_por_mes = defaultdict(lambda: defaultdict(float))
    meses_set = set()

    for p in parcelas:
        data_vencimento = p['data_vencimento']
        valor = float(p['valor_parcela'])
        bandeira_nome = p['bandeira_nome'] or "DESCONHECIDA"
        chave_bandeira = f"{bandeira_nome} - {p['vencimento_bandeira']}"

        chave_mes_ano = data_vencimento.strftime("%m/%Y")
        meses_set.add(chave_mes_ano)

        parcelas_por_mes[chave_bandeira][chave_mes_ano] += valor

    colunas_meses = sorted(meses_set, key=lambda x: datetime.strptime(x, "%m/%Y"))

    conn.close()

    return render_template('dashboard.html',
                          parcelas=parcelas,
                          parcelas_por_mes=parcelas_por_mes,
                          colunas_meses=colunas_meses)


@app.route('/cadastro/<tipo>', methods=['GET', 'POST'])
def cadastro(tipo):
    if request.method == 'POST':
        nome = request.form['nome']
        conn = get_db_connection()

        try:
            if tipo.lower() == 'parcelamento':
                conn.execute("INSERT INTO PARCELAMENTO (tipo) VALUES (?)", (nome,))
            else:
                conn.execute(f"INSERT INTO {tipo.upper()} (nome) VALUES (?)", (nome,))
            conn.commit()
        except Exception as e:
            flash(f"Erro ao cadastrar {tipo}: {str(e)}", "danger")
        finally:
            conn.close()

        return redirect(url_for('cadastro', tipo=tipo))

    return render_template('cadastro.html', tipo=tipo)

@app.route('/despesas', methods=['GET', 'POST'])

def lancar_despesas():
    conn = get_db_connection()

    if request.method == 'POST':
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
                request.form['valor_parcela']
            )

            # Verifica se todos os campos foram preenchidos
            if not all(dados):
                flash("Todos os campos devem ser preenchidos.", "danger")
                return redirect(url_for('lancar_despesas'))

            cursor = conn.cursor()

            # Insere a despesa (sem vencimento_bandeira_id e melhor_dia_compra_id)
            cursor.execute("""
                INSERT INTO DESPESAS (
                    estabelecimento_id, categoria_id, local_compra_id, comprador_id,
                    produto_id, data_compra, valor_compra, forma_pagamento_id, bandeira_id,
                    parcelamento_id, quantidade_parcelas_id, valor_parcela
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    return render_template('despesas.html', 
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
            P.nome AS produto_nome,
            D.valor_compra,
            D.data_compra,
            FP.nome AS forma_pagamento,
            B.nome AS bandeira_nome,
            PQP.tipo AS parcelamento_tipo,
            D.valor_parcela
        FROM DESPESAS D
        LEFT JOIN PRODUTO P ON D.produto_id = P.id
        LEFT JOIN FORMA_PAGAMENTO FP ON D.forma_pagamento_id = FP.id
        LEFT JOIN BANDEIRA B ON D.bandeira_id = B.id
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



from datetime import datetime
from dateutil.relativedelta import relativedelta

@app.route('/editar_despesa/<int:id>', methods=['GET', 'POST'])
def editar_despesa(id):
    conn = get_db_connection()
    despesa = conn.execute("SELECT * FROM DESPESAS WHERE id = ?", (id,)).fetchone()

    if not despesa:
        flash("Despesa não encontrada!", "danger")
        return redirect(url_for('consultar_despesas'))

    if request.method == 'POST':
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
                request.form['valor_parcela']
            )

            # Atualiza a despesa
            conn.execute("""
                UPDATE DESPESAS
                SET estabelecimento_id = ?, categoria_id = ?, local_compra_id = ?, comprador_id = ?,
                    produto_id = ?, data_compra = ?, valor_compra = ?, forma_pagamento_id = ?, bandeira_id = ?,
                    parcelamento_id = ?, quantidade_parcelas_id = ?, valor_parcela = ?
                WHERE id = ?
            """, (*dados, id))
            conn.commit()

            # Busca nova quantidade de parcelas e dados da bandeira
            nova_qtd_parcelas = int(conn.execute(
                "SELECT quantidade FROM QUANTIDADE_PARCELAS WHERE id = ?",
                (request.form['quantidade_parcelas_id'],)
            ).fetchone()['quantidade'])

            bandeira_id = request.form['bandeira_id']
            bandeira_dados = conn.execute(
                "SELECT melhor_dia_compra, vencimento_dia FROM BANDEIRA WHERE id = ?",
                (bandeira_id,)
            ).fetchone()

            melhor_dia_compra = bandeira_dados['melhor_dia_compra']
            vencimento_dia = bandeira_dados['vencimento_dia']
            nova_data_compra = datetime.strptime(request.form['data_compra'], "%d/%m/%Y")
            novo_valor_parcela = float(request.form['valor_parcela'])

            # Define data da primeira parcela
            if nova_data_compra.day < melhor_dia_compra:
                primeira_data = nova_data_compra.replace(day=1) + relativedelta(months=1)
            else:
                primeira_data = nova_data_compra.replace(day=1) + relativedelta(months=2)

            try:
                primeira_data = primeira_data.replace(day=vencimento_dia)
            except ValueError:
                primeira_data = (primeira_data + relativedelta(months=1, day=1)) - relativedelta(days=1)

            # Gera novas datas
            datas_novas = [primeira_data + relativedelta(months=i) for i in range(nova_qtd_parcelas)]

            # Parcelas existentes
            parcelas_existentes = conn.execute(
                "SELECT * FROM PARCELAS WHERE despesa_id = ? ORDER BY numero_parcela", (id,)
            ).fetchall()
            qtd_parcelas_atual = len(parcelas_existentes)

            # Adiciona novas parcelas
            if nova_qtd_parcelas > qtd_parcelas_atual:
                for i in range(qtd_parcelas_atual, nova_qtd_parcelas):
                    conn.execute("""
                        INSERT INTO PARCELAS (despesa_id, data_vencimento, valor_parcela, numero_parcela)
                        VALUES (?, ?, ?, ?)
                    """, (id, datas_novas[i].strftime("%d/%m/%Y"), novo_valor_parcela, i + 1))

            # Remove parcelas excedentes
            elif nova_qtd_parcelas < qtd_parcelas_atual:
                for i in range(nova_qtd_parcelas, qtd_parcelas_atual):
                    conn.execute("""
                        DELETE FROM PARCELAS WHERE despesa_id = ? AND numero_parcela = ?
                    """, (id, i + 1))

            # Atualiza parcelas existentes
            for i, parcela in enumerate(parcelas_existentes[:nova_qtd_parcelas]):
                conn.execute("""
                    UPDATE PARCELAS
                    SET data_vencimento = ?, valor_parcela = ?
                    WHERE id = ?
                """, (datas_novas[i].strftime("%d/%m/%Y"), novo_valor_parcela, parcela['id']))

            conn.commit()
            flash("Despesa atualizada com sucesso!", "success")
            return redirect(url_for('consultar_despesas'))

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao atualizar despesa: {e}", "danger")
            print("Erro:", e)

    # Carrega os dados do formulário para GET
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

    return render_template('editar_despesa.html',
                           despesa=despesa,
                           estabelecimentos=estabelecimentos,
                           categorias=categorias,
                           locais=locais,
                           compradores=compradores,
                           produtos=produtos,
                           formas=formas,
                           bandeiras=bandeiras,
                           parcelamentos=parcelamentos,
                           quantidades=quantidade_parcelas)

                       
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


@app.route('/cadastro/<tipo>/consultar')
def consultar_cadastro(tipo):
    conn = get_db_connection()
    try:
        registros = conn.execute(f"SELECT * FROM {tipo.upper()} ORDER BY nome").fetchall()
    except Exception as e:
        registros = []
        flash(f"Erro ao consultar {tipo}: {str(e)}", "danger")
    finally:
        conn.close()
    return render_template('consultar_cadastro.html', tipo=tipo, registros=registros)


@app.route('/cadastro/<tipo>/editar/<int:id>', methods=['GET', 'POST'])
def editar_cadastro(tipo, id):
    conn = get_db_connection()
    if request.method == 'POST':
        nome = request.form['nome']
        conn.execute(f"UPDATE {tipo.upper()} SET nome = ? WHERE id = ?", (nome, id))
        conn.commit()
        conn.close()
        flash(f"{tipo.capitalize()} atualizado com sucesso!", "success")
        return redirect(url_for('consultar_cadastro', tipo=tipo))

    registro = conn.execute(f"SELECT * FROM {tipo.upper()} WHERE id = ?", (id,)).fetchone()
    conn.close()
    return render_template('editar_cadastro.html', tipo=tipo, registro=registro)


@app.route('/cadastro/<tipo>/excluir/<int:id>', methods=['POST'])
def excluir_cadastro(tipo, id):
    conn = get_db_connection()
    conn.execute(f"DELETE FROM {tipo.upper()} WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash(f"{tipo.capitalize()} excluído com sucesso!", "success")
    return redirect(url_for('consultar_cadastro', tipo=tipo))


# estabelecimento
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


# CONSULTAR ESTABELECIMENTOS
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


# EDITAR ESTABELECIMENTO
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



# EXCLUIR ESTABELECIMENTO
@app.route('/estabelecimento/excluir/<int:id>', methods=['POST'])
def excluir_estabelecimento(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM ESTABELECIMENTO WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Estabelecimento excluído com sucesso!", "success")
    return redirect(url_for('listar_estabelecimentos'))


#Rota para Categoria 
@app.route('/cadastro/categoria/novo', methods=['GET', 'POST'])
def nova_categoria():
    if request.method == 'POST':
        nome = request.form['nome']
        conn = get_db_connection()
        conn.execute("INSERT INTO CATEGORIA (nome) VALUES (?)", (nome,))
        conn.commit()
        conn.close()
        flash("Categoria cadastrada com sucesso!", "success")
        return redirect(url_for('listar_categorias'))
    return render_template('editar_categoria.html', registro=None, tipo='categoria')


@app.route('/cadastro/categoria')
def consultar_categoria():
    conn = get_db_connection()
    categorias = conn.execute("SELECT * FROM CATEGORIA ORDER BY nome").fetchall()
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
        novo_nome = request.form['nome']
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


#local da compra
@app.route('/cadastro/local_compra/novo', methods=['GET', 'POST'])
def novo_local_compra():
    if request.method == 'POST':
        nome = request.form['nome']
        conn = get_db_connection()
        conn.execute("INSERT INTO LOCAL_COMPRA (nome) VALUES (?)", (nome,))
        conn.commit()
        conn.close()
        flash("Local da compra cadastrado com sucesso!", "success")
        return redirect(url_for('listar_local_compra'))
    return render_template('editar_local_compra.html', registro=None, tipo='local_compra')


@app.route('/cadastro/local_compra')
def consultar_local_compra():
    conn = get_db_connection()
    locais = conn.execute("SELECT * FROM LOCAL_COMPRA ORDER BY nome").fetchall()
    conn.close()
    return render_template('consultar_local_compra.html', local_compras=locais)

@app.route('/cadastro/local_compra/editar/<int:id>', methods=['GET', 'POST'])
def editar_local_compra(id):
    conn = get_db_connection()
    local_compra = conn.execute("SELECT * FROM LOCAL_COMPRA WHERE id = ?", (id,)).fetchone()

    if not local_compra:
        flash("Categoria não encontrada.", "danger")
        return redirect(url_for('listar_local_compra'))

    if request.method == 'POST':
        novo_nome = request.form['nome']
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

#produtos
@app.route('/cadastro/produto/novo', methods=['GET', 'POST'])
def novo_produto():
    if request.method == 'POST':
        nome = request.form['nome']
        conn = get_db_connection()
        conn.execute("INSERT INTO PRODUTO (nome) VALUES (?)", (nome,))
        conn.commit()
        conn.close()
        flash("Produto cadastrado com sucesso!", "success")
        return redirect(url_for('listar_produtos'))
    return render_template('editar_produto.html', registro=None, tipo='produto')

@app.route('/cadastro/produto')
def consultar_produto():
    conn = get_db_connection()
    produtos = conn.execute("SELECT * FROM PRODUTO ORDER BY nome").fetchall()
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
        novo_nome = request.form['nome']
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


 #bandeiras 

@app.route('/cadastro/bandeira/novo', methods=['GET', 'POST'])
def nova_bandeira():
    if request.method == 'POST':
        nome = request.form['nome']
        vencimento_dia = request.form['vencimento_dia']
        melhor_dia_compra = request.form['melhor_dia_compra']
        
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO BANDEIRA (nome, vencimento_dia, melhor_dia_compra) VALUES (?, ?, ?)",
            (nome, vencimento_dia, melhor_dia_compra)
        )
        conn.commit()
        conn.close()
        flash("Bandeira cadastrada com sucesso!", "success")
        return redirect(url_for('listar_bandeiras'))
    
    return render_template('editar_bandeira.html', registro=None, tipo='bandeira')


@app.route('/cadastro/bandeira')
def consultar_bandeira():
    conn = get_db_connection()
    bandeiras = conn.execute("SELECT * FROM bandeira ORDER BY nome").fetchall()
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
        novo_nome = request.form.get('nome')
        novo_vencimento_dia = request.form.get('vencimento_dia')
        novo_melhor_dia_compra = request.form.get('melhor_dia_compra')

        if not (novo_nome and novo_vencimento_dia and novo_melhor_dia_compra):
            flash("Todos os campos devem ser preenchidos.", "warning")
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


#forma de pagamento
@app.route('/cadastro/forma_pagamento/novo', methods=['GET', 'POST'])
def nova_forma_pagamento():
    if request.method == 'POST':
        nome = request.form['nome']
        conn = get_db_connection()
        conn.execute("INSERT INTO FORMA_PAGAMENTO (nome) VALUES (?)", (nome,))
        conn.commit()
        conn.close()
        flash("Forma de Pagamento cadastrada com sucesso!", "success")
        return redirect(url_for('listar_formas_pagamento'))
    return render_template('editar_forma_pagamento.html', registro=None, tipo='forma_pagamento')

@app.route('/cadastro/forma_pagamento')
def consultar_forma_pagamento():
    conn = get_db_connection()
    forma_pagamento= conn.execute("SELECT * FROM FORMA_PAGAMENTO ORDER BY nome").fetchall()
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
        novo_nome = request.form['nome']
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

#comprador
@app.route('/cadastro/comprador/novo', methods=['GET', 'POST'])
def novo_comprador():
    if request.method == 'POST':
        nome = request.form['nome']
        conn = get_db_connection()
        conn.execute("INSERT INTO COMPRADOR (nome) VALUES (?)", (nome,))
        conn.commit()
        conn.close()
        flash("Comprador cadastrado com sucesso!", "success")
        return redirect(url_for('listar_comprador'))
    return render_template('editar_comprador.html', registro=None, tipo='comprador')


@app.route('/cadastro/comprador')
def consultar_comprador():
    conn = get_db_connection()
    comprador = conn.execute("SELECT * FROM COMPRADOR ORDER BY nome").fetchall()
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
        novo_nome = request.form['nome']
        conn.execute("UPDATE COMPRADOR SET nome = ? WHERE id = ?", (novo_nome, id))
        conn.commit()
        conn.close()
        flash("Comprador atualizado com sucesso!", "success")
        return redirect(url_for('listar_comprador'))

    conn.close()
    return render_template('editar_produto.html', registro=comprador, tipo='comprador')

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



from flask import jsonify

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


@app.route('/logout')
def logout():
    session.clear()  # limpa toda a sessão do usuário (remove login)
    flash('Você saiu do sistema com sucesso.', 'success')
    return redirect(url_for('login'))  # redireciona para a página de login

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario'].strip()
        senha = request.form['senha'].strip()

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM usuario WHERE usuario = ?", (usuario,)).fetchone()
        conn.close()

        if user and check_password_hash(user['senha_hash'], senha):
            session['user_id'] = user['usuario']  # ou user['id'] se preferir armazenar o id
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('dashboard_login'))  # página após login
        else:
            flash('Usuário ou senha incorretos.', 'danger')

    return render_template('login.html')
@app.route('/')
def dashboard_login():
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    return render_template('dashboard_login.html', usuario=session['user_id'])

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

if __name__ == '__main__':
    app.secret_key = 'segredo-super-seguro'
    app.run(debug=True)
