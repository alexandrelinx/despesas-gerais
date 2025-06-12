from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict

def calcular_parcelas_neon(data_compra, quantidade_parcelas, vencimento_dia, melhor_dia_compra):
    # Define o próximo "melhor dia de compra"
    melhor_data_corte = data_compra.replace(day=melhor_dia_compra)
    if data_compra.day > melhor_dia_compra:
        melhor_data_corte += relativedelta(months=1)

    # Se comprou antes do corte, vai para a próxima fatura
    if data_compra < melhor_data_corte:
        primeiro_mes = data_compra + relativedelta(months=1)
    else:
        primeiro_mes = data_compra + relativedelta(months=2)

    # Ajusta o vencimento
    try:
        primeira_parcela = primeiro_mes.replace(day=vencimento_dia)
    except ValueError:
        proximo_mes = primeiro_mes + relativedelta(months=1, day=1)
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
