"""Plano B: lê o espelho por OCR quando o PDF não tem texto (escaneado) ou
quando o aluno envia uma imagem (print da tela).

Tudo é opcional: se o rapidocr não estiver instalado, levanta OcrIndisponivel
e o site mostra uma mensagem amigável. O arquivo enviado nunca é salvo.
"""
import io

from .espelho import EspelhoInvalido, EspelhoSemTexto, interpretar_paginas

ESCALA_PDF = 2.5                       # resolução da página renderizada para o OCR
EXTENSOES_IMAGEM = ('.png', '.jpg', '.jpeg')
MENSAGEM_NAO_LEU = 'Não conseguimos ler este arquivo. Envie o PDF original do SAU ou um print reto da tela.'

_motor = None                          # o RapidOCR demora para carregar: só na primeira vez


class OcrIndisponivel(Exception):
    pass


def motor_ocr():
    global _motor
    if _motor is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            raise OcrIndisponivel(MENSAGEM_NAO_LEU)
        _motor = RapidOCR()
    return _motor


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
            return [Image.open(io.BytesIO(conteudo)).convert('RGB')]
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(conteudo)
        return [pagina.render(scale=ESCALA_PDF).to_pil().convert('RGB') for pagina in pdf]
    except ImportError:
        raise OcrIndisponivel(MENSAGEM_NAO_LEU)
    except Exception:
        raise EspelhoInvalido(MENSAGEM_NAO_LEU)


def palavras_da_imagem(imagem):
    """Caixas do OCR no mesmo formato de palavras do pdfplumber (text, x0, x1, top, bottom)."""
    import numpy
    resultado, _ = motor_ocr()(numpy.array(imagem))
    palavras = []
    for caixa, texto, confianca in resultado or []:
        xs = [ponto[0] for ponto in caixa]
        ys = [ponto[1] for ponto in caixa]
        palavras.append({
            'text': texto, 'x0': min(xs), 'x1': max(xs), 'top': min(ys), 'bottom': max(ys),
            'conf': float(confianca),
        })
    return palavras


def extrair_palavras_ocr(arquivo):
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
        })
    return paginas


def ler_espelho_por_ocr(arquivo):
    """Mesmo dicionário de ler_espelho. Erros viram a mensagem amigável."""
    try:
        dados = interpretar_paginas(extrair_palavras_ocr(arquivo))
    except (EspelhoInvalido, EspelhoSemTexto):
        raise EspelhoInvalido(MENSAGEM_NAO_LEU)
    if not dados['disciplinas']:
        raise EspelhoInvalido(MENSAGEM_NAO_LEU)
    return dados
