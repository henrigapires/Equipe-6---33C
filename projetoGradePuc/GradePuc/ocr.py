"""Plano B: lê o espelho por OCR quando o PDF não tem texto (escaneado) ou
quando o aluno envia uma imagem (print da tela).

Tudo é opcional: se o rapidocr não estiver instalado, levanta OcrIndisponivel
e o site mostra uma mensagem amigável. O arquivo enviado nunca é salvo.
"""
import importlib.util
import io

from .espelho import (
    EspelhoInvalido, EspelhoSemTexto, altura_tipica, centro_y, faixa_dos_valores_do_curso,
    interpretar_paginas, log, rotulos_do_curso_ocr,
)

ESCALA_PDF = 2.5                       # resolução da página renderizada para o OCR
EXTENSOES_IMAGEM = ('.png', '.jpg', '.jpeg')
LARGURA_MINIMA = 1800                  # prints mais estreitos são ampliados antes do OCR
# OCR instalado, mas a leitura não deu certo: o que o aluno pode fazer
MENSAGEM_NAO_LEU = (
    'Não conseguimos ler as disciplinas deste arquivo. O print precisa mostrar a tabela com as '
    'colunas Período, Disciplina e Situação, sem cortar as colunas. Se o espelho não coube num '
    'print só, selecione todos os prints de uma vez. Ou envie o PDF do espelho '
    '(no SAU, Imprimir → Salvar como PDF).'
)
# OCR não instalado neste computador (Python 3.13+ ou requirements não instalados)
MENSAGEM_SEM_OCR = (
    'A leitura de prints não está instalada neste computador. Envie o PDF do espelho: no SAU, '
    'Imprimir → Salvar como PDF. Ou instale com pip install -r requirements.txt, com Python 3.12 ou anterior.'
)
PARAMETROS_DO_MOTOR = {
    # Print de tela nunca está de cabeça para baixo. Sem o classificador de ângulo o OCR
    # não "desvira" caixas por engano (o CR 8,9 era lido como 6'8).
    'use_cls': False,
    # Limiares mais baixos: o OCR passa a achar números soltos e miúdos (créditos, "0", "1").
    'box_thresh': 0.3,
    'text_score': 0.3,
}
ESCALA_RECORTE = 3                     # ampliação do pedaço lido de novo (valor que faltou)

_motor = None                          # o RapidOCR demora para carregar: só na primeira vez


class OcrIndisponivel(Exception):
    pass


def motor_ocr():
    global _motor
    if _motor is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            log.warning('leitura de prints indisponível: rapidocr_onnxruntime não está instalado')
            raise OcrIndisponivel(MENSAGEM_SEM_OCR)
        _motor = RapidOCR()
    return _motor


def ocr_instalado():
    """O pacote do OCR está instalado? (Só procura o pacote, não carrega o modelo.)"""
    return importlib.util.find_spec('rapidocr_onnxruntime') is not None


def eh_imagem(nome):
    return nome.lower().endswith(EXTENSOES_IMAGEM)


def conteudo_do_arquivo(arquivo):
    """Bytes de um caminho ou de um arquivo enviado pelo Django (sem gravar nada)."""
    if hasattr(arquivo, 'read'):
        if hasattr(arquivo, 'seek'):
            arquivo.seek(0)
        return arquivo.read()
    with open(arquivo, 'rb') as f:
        return f.read()


def imagens_do_arquivo(conteudo, nome):
    try:
        from PIL import Image
        if eh_imagem(nome):
            imagem = Image.open(io.BytesIO(conteudo)).convert('RGB')
            if imagem.width < LARGURA_MINIMA:
                # print pequeno: amplia para o OCR enxergar números miúdos (ex.: créditos)
                escala = LARGURA_MINIMA / imagem.width
                imagem = imagem.resize((LARGURA_MINIMA, round(imagem.height * escala)), Image.LANCZOS)
            return [imagem]
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(conteudo)
        return [pagina.render(scale=ESCALA_PDF).to_pil().convert('RGB') for pagina in pdf]
    except ImportError as erro:
        log.warning('leitura de prints indisponível: falta %s', erro.name)
        raise OcrIndisponivel(MENSAGEM_SEM_OCR)
    except Exception as erro:
        log.warning('arquivo enviado não abre como imagem/PDF (%s)', type(erro).__name__)
        raise EspelhoInvalido(MENSAGEM_NAO_LEU)


def caixas_do_ocr(imagem, deslocamento=(0, 0), escala=1):
    """Roda o OCR e devolve as caixas no formato de palavras do pdfplumber
    (text, x0, x1, top, bottom). 'deslocamento' e 'escala' levam as caixas de um recorte
    ampliado de volta para a posição na imagem inteira."""
    import numpy
    resultado, _ = motor_ocr()(numpy.array(imagem), **PARAMETROS_DO_MOTOR)
    dx, dy = deslocamento
    palavras = []
    for caixa, texto, confianca in resultado or []:
        xs = [dx + ponto[0] / escala for ponto in caixa]
        ys = [dy + ponto[1] / escala for ponto in caixa]
        palavras.append({
            'text': texto, 'x0': min(xs), 'x1': max(xs), 'top': min(ys), 'bottom': max(ys),
            'conf': float(confianca),
        })
    return palavras


def valores_que_faltaram(imagem, palavras):
    """O OCR às vezes não enxerga um valor curto do quadro do curso (o '0' do código do
    currículo). Para cada rótulo sem nada embaixo, lê de novo só aquele pedaço, ampliado."""
    from PIL import Image
    rotulos = rotulos_do_curso_ocr(palavras)
    if not rotulos:
        return []
    h = altura_tipica(palavras)
    topo, fim = faixa_dos_valores_do_curso(palavras, rotulos)
    dos_rotulos = {id(w) for w in rotulos.values()}
    novas = []
    for rotulo in rotulos.values():
        x0, x1 = rotulo['x0'] - h, rotulo['x1'] + h
        tem_valor = any(
            id(w) not in dos_rotulos and topo < centro_y(w) < fim and x0 < (w['x0'] + w['x1']) / 2 < x1
            for w in palavras
        )
        if tem_valor:
            continue
        caixa = (max(0, int(x0)), max(0, int(topo)), min(imagem.width, int(x1)), min(imagem.height, int(fim)))
        if caixa[2] <= caixa[0] or caixa[3] <= caixa[1]:
            continue
        recorte = imagem.crop(caixa)
        ampliado = recorte.resize((recorte.width * ESCALA_RECORTE, recorte.height * ESCALA_RECORTE), Image.LANCZOS)
        margem = 100     # o OCR acha melhor o texto com um pouco de fundo branco em volta
        fundo = Image.new('RGB', (ampliado.width + 2 * margem, ampliado.height + 2 * margem), 'white')
        fundo.paste(ampliado, (margem, margem))
        deslocamento = (caixa[0] - margem / ESCALA_RECORTE, caixa[1] - margem / ESCALA_RECORTE)
        novas.extend(caixas_do_ocr(fundo, deslocamento, ESCALA_RECORTE))
    return novas


def palavras_da_imagem(imagem):
    palavras = caixas_do_ocr(imagem)
    return palavras + valores_que_faltaram(imagem, palavras)


def extrair_palavras_ocr(arquivo, numero=0):
    """Páginas (caixas do OCR) de um arquivo. 'numero' marca de qual arquivo a página veio."""
    nome = getattr(arquivo, 'name', None) or str(arquivo)
    paginas = []
    for imagem in imagens_do_arquivo(conteudo_do_arquivo(arquivo), nome):
        palavras = palavras_da_imagem(imagem)
        em_ordem = sorted(palavras, key=lambda w: (w['top'], w['x0']))
        paginas.append({
            'palavras': palavras,
            'texto': '\n'.join(w['text'] for w in em_ordem),
            'altura': imagem.height,
            'largura': imagem.width,
            'ocr': True,
            'arquivo': numero,
        })
    return paginas


def conferir_com_o_banco(dados):
    """Na leitura por OCR, o banco sabe mais que o OCR:
    - código com uma letra perdida ('FS4001') vira o código conhecido com os mesmos dígitos
      ('FIS4001'); se não houver um só candidato, a linha continua marcada para conferir;
    - nome e créditos de um código conhecido vêm do banco (o OCR perde espaços:
      'CALCULOA VARIASVARIAVEISI')."""
    from .historico import dados_oficiais, reparar_codigo
    for d in dados['disciplinas']:
        if d.get('confira'):
            consertado = reparar_codigo(d['codigo'])
            if consertado:
                d['codigo'] = consertado
                del d['confira']
        oficial = dados_oficiais(d['codigo'])
        if oficial:
            nome, creditos = oficial
            d['nome'] = nome
            if creditos:
                d['creditos'] = creditos
    return dados


def ler_espelho_por_ocr(arquivos):
    """Mesmo dicionário de ler_espelho. Aceita um arquivo ou uma lista de prints, em
    qualquer ordem (o print com o cabeçalho é achado sozinho). Erros viram a mensagem amigável."""
    if not isinstance(arquivos, (list, tuple)):
        arquivos = [arquivos]
    paginas = []
    for numero, arquivo in enumerate(arquivos):
        paginas.extend(extrair_palavras_ocr(arquivo, numero))
    resumo = ', '.join(f"arquivo {p['arquivo']}: {len(p['palavras'])} caixas" for p in paginas)
    try:
        dados = interpretar_paginas(paginas)
    except (EspelhoInvalido, EspelhoSemTexto) as erro:
        log.warning('espelho por OCR não lido (%s). %s', erro, resumo)
        raise EspelhoInvalido(MENSAGEM_NAO_LEU)
    if not dados['disciplinas']:
        log.warning('espelho por OCR sem nenhuma disciplina (só o quadro do curso?). %s', resumo)
        raise EspelhoInvalido(MENSAGEM_NAO_LEU)
    log.info('espelho por OCR lido: %d disciplina(s), contagem %s. %s', len(dados['disciplinas']), dados.get('ocr'), resumo)
    return conferir_com_o_banco(dados)
