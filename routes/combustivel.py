from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify, Response, make_response
from util.helpers import calcular_valor_pago
from util.helpers import calcular_consumo
from util.helpers import obter_dados_por_mes
from util.helpers import converter_para_ddmmYYYY
from util.helpers import get_db_connection
from io import BytesIO
from io import StringIO
from os
from flask import render_template
from flask import Response
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
from collections import defaultdict
from reportlab.lib.pagesizes import letter, landscape

#combustivel_bp = Blueprint('combustivel', __name__, url_prefix='/outros/combustivel')
app = Flask(__name__)
app.config['SECRET_KEY'] = 'despesas'  



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

@app.route('/outros/combustivel/deletar/<int:id>')
def deletar_combustivel(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM combustivel WHERE id=?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('combustivel'))

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








    if __name__ == '__main__':
    app.secret_key = 'segredo-super-seguro'
    app.run(debug=True)

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
