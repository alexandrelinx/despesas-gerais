from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict

def calcular_parcelas(data_compra, quantidade_parcelas, vencimento_bandeira, melhor_dia_compra):
    try:
        # Assume que data_compra sempre vem no formato "dd/mm/yyyy"
        data_compra = datetime.strptime(data_compra, "%d/%m/%Y")
    except Exception as e:
        print(f"Erro ao converter data: {data_compra} -> {e}")
        return []

    parcelas = []

    # Ajuste para determinar a primeira parcela com base no melhor dia de compra
    if data_compra.day < melhor_dia_compra:
        # Se a compra for antes do melhor dia, a primeira parcela será no vencimento do mês seguinte
        if data_compra.month == 12:
            primeira_parcela = data_compra.replace(year=data_compra.year + 1, month=1, day=vencimento_bandeira)
        else:
            primeira_parcela = data_compra.replace(month=data_compra.month + 1, day=vencimento_bandeira)
    else:
        # Se a compra for depois do melhor dia, a primeira parcela será no vencimento do mês seguinte
        if data_compra.month == 12:
            primeira_parcela = data_compra.replace(year=data_compra.year + 1, month=1, day=vencimento_bandeira)
        else:
            primeira_parcela = data_compra.replace(month=data_compra.month + 1, day=vencimento_bandeira)

    # Garantir que o vencimento da primeira parcela seja o vencimento da bandeira
    try:
        primeira_parcela = primeira_parcela.replace(day=vencimento_bandeira)
    except ValueError:
        # Caso o dia seja inválido (ex: fevereiro 30), ajusta para o último dia do mês
        ultima_do_mes = (primeira_parcela + relativedelta(months=1, day=1)) - relativedelta(days=1)
        primeira_parcela = ultima_do_mes

    # Gerar as parcelas
    for i in range(quantidade_parcelas):
        vencimento = primeira_parcela + relativedelta(months=i)
        parcelas.append(vencimento)

    return parcelas


# Função para obter os totais por bandeira e mês
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
            # Usar o formato de mês/ano para identificar cada vencimento
            mes_ano = parcela.strftime("%m/%Y")  # Ex: 06/2025
            bandeira = d['bandeira_nome']
            total = d['valor_parcela']
            
            # Somando os totais por mês e bandeira
            totais_agrupados[(mes_ano, bandeira)] += total
    
    # Converter totais agrupados para lista
    totais_finais = [{'mes_ano': mes_ano, 'bandeira': bandeira, 'total': total} 
                     for (mes_ano, bandeira), total in totais_agrupados.items()]
    
    return totais_finais
