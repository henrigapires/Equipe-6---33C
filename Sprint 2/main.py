def calcula_divisao_inteira(x, y):
    return x//y

def calcula_potenciacao(x, y):
    return x ** y

def calcula_radiciacao(x, y):
    if y == 0:
        return None
    elif x < 0 and y % 2 == 0:
        print("Não existe raiz real de número negativo para índices pares.")
        return None
    else:
        if x < 0:
            return -((-x) ** (1 / y))
        return x ** (1 / y)

#fazer as funções acima (com os nomes de acordo com o BP lá embaixo)

while cod_operacao != 0:

    cod_operacao=int(input('''Digite o número da operação desejada:

1 - Adição
2 - Subtração
3 - Mulitplicação
4 - Divisão
5 - Potenciação
6 - Radiciação
7 - Divisão inteira
8 - Resto
9 - Percentual
0 - Sair do programa'''))

    if cod_operacao == 1:
        a=float(input("Digite o primeiro número: "))
        b=float(input("Digite o segundo número: "))
        print(f' {a} + {b} = {calcula_adicao(a, b)}')
    elif cod_operacao == 2:
        a=float(input("Digite o primeiro minuendo: "))
        b=float(input("Digite o segundo subtraendo: "))
        print(f' {a} - {b} = {calcula_subtracao(a, b)}')
    elif cod_operacao == 3:
        a=float(input("Digite o primeiro fator: "))
        b=float(input("Digite o segundo fator: "))
        print(f' {a} * {b} = {calcula_multiplicação(a, b)}')
    elif cod_operacao == 4:
        a=float(input("Digite o dividendo: "))
        b=float(input("Digite o divisor: "))
        print(f' {a} / {b} = {calcula_divisao(a, b)}')
    elif cod_operacao == 5:
        a=float(input("Digite a base: "))
        b=float(input("Digite o expoente: "))
        print(f' {a} ^ {b} = {calcula_potenciacao(a, b)}')
    elif cod_operacao == 6:
        a=float(input("Digite o radicando: "))
        b=float(input("Digite o índice: "))
        print(f' √{a} = {calcula_radiciacao(a, b)}')
    elif cod_operacao == 7:
        a=float(input("Digite o dividendo: "))
        b=float(input("Digite o divisor: "))
        print(f' {a} // {b} = {calcula_divisao_inteira(a, b)}')
    elif cod_operacao == 8:
        a=float(input("Digite o primeiro dividendo: "))
        b=float(input("Digite o segundo divisor: "))
        print(f' Resto da divisão de{a} por {b} = {calcula_resto(a, b)}')
    elif cod_operacao == 9:
        a=float(input("Digite o número: "))
        b=float(input("Digite a porcentagem: "))
        print(f' {b}% de {a} = {calcula_percentual(a, b)}')
    elif cod_operacao == 0:
        print("Saindo do programa...")
    else:
        print("Opção inválida, digite um número de 0 a 9.")





