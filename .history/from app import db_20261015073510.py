import os

def listar_estrutura(path='.', nivel=3, prefix=''):
    linhas = []
    if nivel < 0:
        return linhas
    try:
        itens = sorted(os.listdir(path))
    except Exception as e:
        linhas.append(f"{prefix}[Erro ao acessar: {e}]")
        return linhas
    for i, item in enumerate(itens):
        caminho = os.path.join(path, item)
        connector = '├── '
        if i == len(itens) -1:
            connector = '└── '
        linhas.append(f"{prefix}{connector}{item}")
        if os.path.isdir(caminho):
            extensao = '    ' if i == len(itens) -1 else '│   '
            linhas.extend(listar_estrutura(caminho, nivel -1, prefix + extensao))
    return linhas

def salvar_estrutura_em_log(arquivo_log='estrutura_projeto.log', base_path='.'):
    linhas = listar_estrutura(base_path)
    with open(arquivo_log, 'w', encoding='utf-8') as f:
        f.write('\n'.join(linhas))
    print(f"Estrutura salva em {arquivo_log}")

if __name__ == '__main__':
    salvar_estrutura_em_log()