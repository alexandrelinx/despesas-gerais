from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict

def calcular_parcelas(data_compra, quantidade_parcelas, vencimento_dia, melhor_dia_compra):
    try:
        data_compra = datetime.strptime(data_compra, "%d/%m/%Y")
    except Exception as e:
        print(f"Erro ao converter data: {data_compra} -> {e}")
        return []

    parcelas = []

    # Determina o mês da primeira parcela com base no melhor dia de compra
    if data_compra.day < melhor_dia_compra:
        primeiro_mes = data_compra + relativedelta(months=1)
    else:
        primeiro_mes = data_compra + relativedelta(months=2)

    # Define a data da primeira parcela com o vencimento da bandeira
    try:
        primeira_parcela = primeiro_mes.replace(day=vencimento_dia)
    except ValueError:
        # Ajusta para o último dia do mês caso o dia não exista
        proximo_mes = primeiro_mes + relativedelta(months=1, day=1)
        primeira_parcela = proximo_mes - relativedelta(days=1)

    # Gera as demais parcelas
    for i in range(quantidade_parcelas):
        vencimento = primeira_parcela + relativedelta(months=i)
        parcelas.append(vencimento)

    return parcelas


def obter_dados_dashboard(despesas):
    totais_agrupados = defaultdict(float)

    for d in despesas:
        parcelas = calcular_parcelas(
            d['data_compra'],
            d['quantidade_parcelas'],
            d['vencimento_bandeira'],
            d['melhor_dia_compra']
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

    #return totais_finais
