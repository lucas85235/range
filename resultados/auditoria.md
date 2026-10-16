# Veredito final: sua posição na margem do 2º turno (25/10)

> **Retrato de 16/10, antes das correções.** Já resolvido depois: a porta 8050 ocupada agora dá
> erro (item 1); o gráfico da Polymarket e a nota de início usam o horário de Brasília (item 2);
> o painel e o monitor avisam da falha nos arquivos de município e da parada de ciclos, com 70 min
> de "recuperando" depois (item 4); o README traz o atraso de ~5 min e não chama mais as contas de
> conservadoras (item 5), a justificativa da f90 (item 8 e seção 1), a fonte da resolução (item 17)
> e a lista do item 21; a aba Trade usa 80% por padrão (seção 2). As linhas citadas do README são
> da versão anterior. O checklist da seção 4 continua valendo.

Estes resultados vêm de testes em dados históricos e simulados. Não são recomendação de investimento. Na vida real você só pode **vender**. Tudo o que envolve comprar ou trocar de faixa é simulação.

**Mercados simulados usados nas tabelas:**
- **"como em 4/10":** o preço anda atrás do modelo no ritmo medido na noite real.
- **"mais esperto":** reage mais rápido.
- **"igual ao modelo":** o preço é a própria chance do modelo.

## Resumo

- **Posição real: mantenha `f90@2:100`.** A regra vende tudo no primeiro ciclo em que a faixa de 90% do modelo deixa de tocar a sua, a partir de 2% apurado.
  - Nas simulações ela não tem a maior média.
  - É a que menos erra: em 84 noites montadas com votos reais e resultado perto de 4, nunca vendeu a faixa vencedora e nunca ficou abaixo de segurar.
  - Foi a melhor na noite real de 4/10 com qualquer atraso de até 10 min.
- **Trade simulado: comece em dinheiro.** O limiar de 80% serve para ter menos noites com prejuízo, não para ganhar mais: o de 70% tem média maior. O lucro do trade depende de o mercado andar atrás do modelo e desaparece com um viés de cerca de 1,5 ponto.
- **O maior risco do dia 25 é operacional, não a regra.** Os pontos são:
  - um painel velho escutando na porta 8050;
  - o relógio do PC 1 h atrás de Brasília;
  - o PC suspender ou ficar sem rede;
  - falha silenciosa nos arquivos de município do TSE;
  - o som do painel desligado.
- **Reaja rápido ao aviso.** Do TSE até a sua venda, o atraso real é de cerca de 5 min (de 2,4 a 8,6), não 1 a 1,5 min como diz o README. Na noite de 4/10, a janela útil para vender foi de uns 10 min.

---

## 1. Posição real (só venda)

### Recomendação

| Sua posição | Regra | Observação |
|---|---|---|
| Sim "F <4%" | `f90@2:100` sozinha | Um piso de preço não ajuda. Nas noites que terminam entre 3 e 5, ele custa de US$ 3 a 4 por US$ 100. |
| Sim "F 4-8%" | `f90@2:100`, mais um piso manual opcional: vender se o preço cair abaixo de 15¢ | O ganho é pequeno: +US$ 4,85 por US$ 100 em média, à frente em 79% dos cenários. |

Se usar o piso de 15¢, siga três condições:
- só depois de 2% apurado (sem essa trava, o stop disparou com 0,37% apurado num caminho real e deixou US$ 2 contra 247);
- olhando o preço médio, não um bid de um instante;
- com o preço abaixo de 15¢ por alguns minutos seguidos.

O monitor não tem esse degrau, então essa venda seria manual.

### Por que a f90@2

Noite real de 4/10, com o preço real da Polymarket (faixas de 5 pontos) e US$ 100 na faixa que perdeu ("L <5%"):

| Regra | D=2 min | D=5 | D=10 | D=15 |
|---|---|---|---|---|
| f90@2 | 91 (17h30) | 84 (17h33) | 82 (17h38) | 47 (17h43) |
| Chance ≤ 20% desde 5% (= escalonada) | 52 | 47 | 44 | 28 |
| Chance ≤ 20% desde 20% | 18 | 20 | 10 | 8 |
| Stop < 15¢ | 23 | 23 | 23 | 23 |
| Segurar | 0 | 0 | 0 | 0 |

D é o atraso entre os dados e a sua ordem.
- Na faixa que ganhou ("F <5%"), nenhuma regra vende: todas terminam em US$ 368.
- Com D de 0 a 10 min, a f90 fica entre 82 e 92. Com D de 11 a 15, cai para 74, 70, 57, 52 e 47, porque o mercado só derrubou o preço entre 17h39 e 17h43.
- Com a taxa de 4%, o resultado em D=5 vai de 84 para 82,2.
- Com ±5¢ de spread vai para 77. Com ±20¢ a f90 ainda lidera (51,7 contra 14,4).

### Quão firme é essa escolha

**O que é firme:**
- **Vender pela f90 é melhor que segurar.** Ganha +41,8 (intervalo de 90%: +37,5 a +46,3) no mercado "como em 4/10" e +18,6 (+16,5 a +20,8) no "mais esperto". Das 51 noites em que as duas diferem, 50 favorecem a f90.
- **Spread, taxa, pesos e preço pago não mudam a ordem das regras.** Isso vale para spread de ±1 a ±5¢, para a taxa, para o preço que você pagou (custo afundado) e para os pesos dos cenários.
- **Nas noites de fronteira com votos reais, ela nunca errou a faixa.** São transições 1º→2º turno de 2014, 2018 e 2022, deslocadas para terminar entre 3 e 5. A f90@2 vendeu a faixa vencedora em 0 de 84 noites; a "chance ≤ 20% desde 2%" vendeu em 13.

**O que não é firme:**
- **Ela não tem a maior média nas simulações.**
  - No mercado "como em 4/10", a "chance ≤ 20% desde 5%" rende uns US$ 7 a 8 a mais por US$ 100. O −14,2 original estava inflado por 5 noites em que Lula vencia por menos de 1 ponto.
  - No "mais esperto", depois dessa correção, a f90 fica US$ 3 a 5 à frente.
- **A noite real não separa a f90 das regras por chance "desde 2%".** Às 17h33, qualquer critério (≤5%, ≤10%, ≤20% ou f90) vendia a 50¢. A vantagem dela naquela noite vem do "desde 2%", e o README (linhas 357-363) mistura as duas coisas.
- **No mercado rápido, o atraso pesa mais nela.**
  - No "mais esperto", ela perde US$ 9,6 de 0 a 10 min de atraso, contra 5,5 da "chance ≤ 20%".
  - Com o atraso provável de cerca de 5 min, o stop fica US$ 6 a 9 à frente nas simulações.
  - Mas o stop é o pior na noite real: 23 contra 84.
- **Com viés grande, ela perde a vantagem fora do mercado lento.** Simulação de Sim "F <4%" somando um viés às 100 noites:

| Viés somado às 100 noites | f90 (como em 4/10 / mais esperto / igual ao modelo) | Vende a vencedora (final 3–4) |
|---|---|---|
| nenhum | 137 / 114 / 98 | 3% |
| +0,5× o erro do 1º turno de 2026 | 133 / 109 / 90 | 21% |
| +1,0× | 120 / 92 / 69 | 79% |
| −0,5× | 143 / 117 / 96 | 10% |
| −1,0× | 117 / 86 / 64 | 34% |
| erro do 2º turno de 2022 | 139 / 115 / 98 | 3% |

Como ler essa tabela:
- Segurar dá US$ 95 em todos os cenários.
- O cenário +1× vem de um teste mais difícil que o do dia 25, com base de 4 anos antes.
- Nas transições do mesmo ano o viés foi menor. Em 2014, foi de cerca de metade do erro de 2026 no começo da noite (×0,5 a 0,6). Em 2018, de um quinto. Em 2022, praticamente zero. O cenário +0,5× equivale mais ou menos ao pior caso do mesmo ano.
- No mercado "como em 4/10", o que bateu com a noite real, a f90 fica acima de segurar em todos os cenários de viés.

### Alternativas avaliadas e por que não trocar

- **`20@2:100`.**
  - A favor: rende US$ 6 a 7 a mais por US$ 100 nas simulações sem viés, já com a cobertura corrigida.
  - Contra: vende a faixa vencedora em 5 de 50 noites com F <4% (a f90, em 1 de 50) e em 7 de 47 nas noites que terminam entre 3 e 5. Perde no mercado "segue a parcial" (−3 a −8). Na grade com custos e viés, fica −3,65 em média contra a f90 e só ganha em 25% dos cenários. Nas noites de fronteira com votos reais, empata na média (141 contra 139 em F <4%; 173 contra 171 em F 4-8%), mas perde US$ 50 a 80 quando o viés vai contra a posição.
- **`10@2:100`.** É a única alternativa defensável, mas troca risco por média, sem ganho claro. Não entrou na grade com custos e viés.
  - Empata com a f90 na noite real.
  - Rende uns US$ 3 a 4 a mais nas simulações, já corrigido.
  - Vende a vencedora em 2 de 50 noites com F <4% e em 0 de 33 com F 4-8%.
- **Escalonada, "chance ≤ 20% desde 20%" e stop sozinho:** todas foram piores na noite real.

**Grade de arrependimento.** São 472 cenários: viés de −2,2 a +2,2, mercado certo ou copiando o erro, atraso de 0 a 8 min e 5 mercados, com custo de 2,7¢ mais a taxa. Valores em US$ por US$ 100, no formato máximo | médio.

| Recorte | f90@2 | 20@2 | f90@2 ou <15¢ |
|---|---|---|---|
| Grade inteira | 40,5 \| 8,0 | 45,7 \| 11,7 | 42,4 \| 4,8 |
| Viés até ±1,1, Sim F <4% | 13,2 \| 3,8 | 21,2 \| 6,4 | 14,9 \| 2,5 |
| Viés até ±1,1, Sim F 4-8% | 20,0 \| 6,4 | 31,1 \| 11,5 | 16,6 \| 2,1 |
| Stop pessimista (decide antes, executa depois) | 40,5 \| 6,9 | 45,6 \| 10,5 | 42,4 \| 5,5 |
| 1¢ sem taxa | 43,0 \| 8,5 | 44,7 \| 11,5 | 39,6 \| 4,1 |

Notas sobre a grade:
- "Viés até ±1,1" é a faixa que as noites com votos reais mostraram (de −1,17 a +1,13).
- Os céticos derrubaram o custo de 2,7¢: o custo real de venda ficou perto de 1¢. Com 1¢, a ordem continua a mesma.
- A grade e as noites de fronteira foram investigadas depois das auditorias e não passaram pelos céticos.

### Vender agora ou levar a posição para a noite

Vender já ao bid de hoje vale de US$ 97 a 98,5 por US$ 100. Com os preços de hoje como pesos, levar a posição com a f90 ganha de vender já em todos os casos testados.

Só valeria vender antes se você der à sua faixa bem menos chance do que o preço indica. Nos mercados eficientes, o limite foi de cerca de 21–27% para F 4-8% (com preço de 32,5¢ no teste) e de 29–36% para F <4% (preço de 40,5¢).

---

## 2. Trade simulado

**Melhor variante: começar em dinheiro.** Escolha o limiar de 80% se a prioridade é não perder. Escolha o de 70% se a prioridade é a média e o mercado anda atrás do modelo.

Mercado "mais esperto", média em US$ por US$ 100, com a fração de noites em prejuízo entre parênteses:

| Variante | Sem atraso | 2 min | 5 min | 10 min | Viés F+1 | Viés F+2 |
|---|---|---|---|---|---|---|
| Dinheiro, 70% | 159 (10%) | 149 | 138 | 127 | 111 (38%) | 84 (55%) |
| Dinheiro, 80% | 143 (5%) | 136 | 129 | 119 | 120 (21%) | 85 (52%) |
| Com posição, 70% | 151 (34%) | 141 (44%) | 129 (55%) | 120 (60%) | 110 | 90 |
| Com posição, 80% | 135 (53%) | 130 (55%) | 123 (62%) | 117 (59%) | 110 | 89 |

**O que é firme:**
- **Começar em dinheiro perde com muito menos frequência que começar com a posição.** No limiar de 80%: 2,7% contra 11,8% das noites em "como em 4/10" e 4,6% contra 53,0% em "mais esperto".
- **O limiar de 70% tem média maior quando o mercado anda atrás do modelo.** A diferença do 80% para o 70% é −36,8 (de −60,2 a −16,2) em "como em 4/10" e −16,4 (de −23,0 a −10,2) em "mais esperto".
- **O limiar de 80% ganha no mercado eficiente e protege num viés moderado.**
  - Tem menos noites de prejuízo e ganha no mercado "sabe mais": +3,8 (de +0,6 a +7,5), com prejuízo em 4,6% das noites contra 11,9%.
  - Com viés de 1 ponto, protege: 120 contra 111, com prejuízo em 21% contra 38%.
  - Com viés de 2 pontos, os dois limiares empatam e perdem.

**O que não é firme:**
- **A vantagem média de dinheiro sobre posição depende dos pesos.** Ela se inverte se a chance de "F <4%" passar de cerca de 43–55%; hoje é 38,7%.
- **O lucro do trade é frágil.**
  - O trade em dinheiro a 70% deixa de lucrar no "mais esperto" a partir de um viés de cerca de +1,4 ponto.
  - Medindo o atraso do mercado em % apurado em vez de minutos, o dinheiro a 80% cai de 312 para 209 no "como em 4/10".
  - A taxa tira mais: 312 vira 303.
- **O argumento "só 80% escapa do erro de 2026" não vale exatamente na configuração do monitor.** No caminho real de 2026 com ordem de chegada, o limiar de 70% também escapa, por 0,2 ponto (o pico da faixa errada foi 69,8%). Os limiares de 60% e 65% caem. A bateria usou a versão sem ordem de chegada.
- **O painel e a bateria não seguem o limiar recomendado.** A aba Trade do painel vem com 70% (painel.html:235 e 1004), e as tabelas principais da bateria também usam 70%.

---

## 3. O que passou despercebido, por prioridade

### Alta: afeta o dia 25

1. **Há um painel velho escutando na porta 8050.** Hoje é o PID 32344, aberto em 15/10.
   - **Impacto:** no Windows, um segundo `painel.py` sobe sem erro, mas quem responde é o velho (40 de 40 pedidos no teste). A aba ao vivo aparece "parado". Se você clicar em "Começar", a sessão roda no processo velho, sem o seu `--faixa`/`--degrau`, e há dois clientes lendo o TSE (−37% de vazão por cliente).
   - **O que fazer:** feche todos os painéis de ensaio ou reinicie o PC. `netstat -ano | findstr :8050` tem de voltar vazio.

2. **O relógio do PC está 1 h atrás de Brasília** (fuso UTC-4).
   - **Impacto:** quem começar às "16h50" do relógio local começa às 17h50 de Brasília. Isso custou de US$ 20 a 29 por US$ 100 no teste: a f90 caiu de 136 para 116,5 em F <4% e de 148 para 119 em F 4-8%. O gráfico da Polymarket no painel também mostra a hora local.
   - **O que fazer:** 16h50 de Brasília são 15h50 no relógio deste PC.

3. **Suspensão e queda de energia.** O buraco de 2h49m em 15/10 começou quando o PC saiu da tomada: houve queda de luz, e o roteador caiu junto. Depois de 180 s na bateria, o PC suspendeu.
   - **Impacto:** na tomada, o PC não suspende sozinho, mas fechar a tampa suspende. Num teste, uma suspensão de 30 min no começo da noite (17h10 às 17h40) fez a f90 disparar errado às 17h41.
   - **O que fazer:** deixe o PC na tomada com a tampa aberta. Configure você mesmo a bateria para não suspender (`powercfg /change standby-timeout-dc 0` e `powercfg /change monitor-timeout-dc 0`). Tenha uma rede de reserva: roteador num nobreak ou o hotspot do celular já pareado.

4. **Falha silenciosa nos arquivos de município** (fonte_tse.py:129-135 engole o erro).
   - **Impacto:** se só esses arquivos falharem por uns 20 min, com o arquivo do Brasil funcionando, a tela parece normal. Na volta, o modelo distorce: a chance da faixa certa caiu de 51% para 7% numa noite de teste. Em outra noite, a f90@2:100 disparou errado com 23,5% apurado. O gatilho é estreito: com 50% de falha, ou só 10 min de falha, não houve efeito.
   - **O que fazer:** compare seções% com eleitorado%. Se as seções sobem, o eleitorado para e a fila cresce, não venda por disparo do modelo até os dois voltarem a andar juntos, uns 10 a 30 min depois. Compare também com o preço da Polymarket.

5. **O atraso real é de cerca de 5 min e as simulações supõem zero.**
   - **Impacto:** nas noites simuladas, o ATRASO de 5 min se anula com o ajuste do ritmo, então a execução sai praticamente sem atraso. A frase do README:679-680 de que as contas são "conservadoras" está errada para as simulações. Só as contas da noite real usam de fato 5 min. O atraso provável é de 5,4 min (de 2,4 a 8,6). Uns 2 min vêm do próprio TSE no nível de município no pico, porque é isso que o monitor lê.
   - **O que fazer:** venda assim que o `>>> PLANO` apitar. Meta de até 5 min, limite de uns 10.

6. **O som depende de clique, aba visível e não recarregar.**
   - **Impacto:** o som começa desligado a cada carga da página, e um F5 desliga. Com a aba escondida, o aviso pode atrasar até ~1 min. Mesmo sem som, o título da aba ganha "(!)" quando algo dispara.
   - **O que fazer:** ligue o Som e ouça o bipe de teste. Mantenha a janela visível e ligue o Som de novo depois de qualquer F5.

7. **A posição salva no navegador passa por cima de `--faixa` e `--degrau`** (painel.html:1419-1421). Degraus com espaço, como "f90 @2:100", passam no Python e são descartados pela página.
   - **O que fazer:** confira no topo da página a faixa, o lado (Sim) e o plano `f90@2:100` "aguardando". Escreva o degrau sem espaços.

### Média: análise e decisão

8. **A noite real só comprova o "desde 2%".** A f90 e as regras "chance desde 2%" venderam no mesmo minuto. A escolha da f90 se apoia em vender menos a faixa vencedora e em aguentar melhor o viés, não só na noite real. Basta corrigir o texto do README (357-363). Não há o que mudar no plano.

9. **As simulações não têm o viés visto na noite real.** O gerador tem a mesma estrutura do modelo, então os números de "vendeu por engano" (2–3% perto de 4) valem para um modelo sem viés. Com metade do erro do 1º turno, vão a 21%. Trate as simulações como o melhor caso. Perto de 4 e antes de ~35% apurado, não trate 90% como certeza.

10. **As vitórias de Lula estavam mal cobertas.** "Lula vence" pesa 20% e tinha só 5 noites, todas entre −1 e 0. Não havia noite abaixo de −1 nem acima de +10, que somam 22% da chance. Isso inflava em cerca de 2× a vantagem das regras por chance. Corrigido, favorece a f90. Afeta os números dos relatórios, não a decisão.

11. **Taxa de 4% (politics_fees).** Ao vender a mercado, a taxa é 0,04·p·(1−p) por cota: cerca de 0,97¢ a 41¢ e 0,82¢ a 29¢. Quem deixa ordem parada no livro não paga taxa. Ela tira cerca de 1% das regras de venda e de 3 a 5% do trade, e o aviso do monitor compara com o bid bruto. Conte ~1¢ por cota a menos. Uma ordem limitada evita a taxa, mas pode não sair numa queda.

12. **Tamanho da posição contra a profundidade do livro.** Só importa acima de ~10–15 mil cotas (~US$ 4–6 mil). Até ~5 mil cotas, a diferença é de no máximo 0,4¢. Compare as suas cotas com "Cotas no bid". Se forem mais, venda em 2 ou 3 ordens.

### Baixa

13. **O arquivo do Brasil é ponto único de falha do ciclo.** O erro aparece na tela ("erro no ciclo") e se recupera sozinho quando o arquivo volta. Confira esse arquivo no pré-voo.
14. **Se o TSE mudar o formato do número do candidato, aparece "sem votos" para sempre.** O formato atual (texto "22"/"13") está confirmado nos arquivos do 1º e do 2º turno de 2026, e o erro seria para o lado seguro: nada dispara.
15. **Votos de teste antes das 17h gastariam o plano.** Hoje é hipotético: o arquivo do TSE está zerado. Comece a sessão às 16h50, não de manhã.
16. **O TSE arredonda a 2 casas.** Uma margem real entre 3,993 e 4,0 pode ser publicada como 4,00 e resolver em F 4-8%. A chance é de cerca de 0,1%.
17. **A resolução é pela imprensa, e o TSE só entra se houver ambiguidade.** No 1º turno o pagamento saiu entre 01h48 e 05h. O README:5 diz que é pelo TSE.
18. **A fronteira exata do lado de Lula e o empate são classificados errado no código.** Não afeta as suas faixas.
19. **O PRECO_HOJE está desatualizado** (F 4-8% passou de 32,5 para 29,5¢). Não muda a ordem das regras.
20. **Os tokens da Polymarket nunca são relidos, e um livro vazio parece atualizado.** Confira se há bid/ask nas 8 faixas.
21. **Correções de texto no README:**
    - 679-680: o atraso "conservador";
    - 357-363: a justificativa da f90;
    - 364: o trade a 80%;
    - 5: a fonte da resolução;
    - 411: "TO não existe";
    - "16h50" sem dizer o fuso.

### Descartados pelos céticos (não use)

- "f90 é a regra que mais aguenta modelo errado": sob erro, a f90, a "≤20% desde 5%" e a escalonada ficam a poucos dólares umas das outras, e quem ganha depende do mercado.
- "≤20% desde 20% fica abaixo de segurar com o mercado certo": ela empata.
- "Mercado que copia o erro e reage rápido deixa todas as regras abaixo de segurar": esse ritmo rápido erra 9,1¢ na noite de 4/10, contra 2,9¢ do ritmo ajustado.
- "Incerteza larga demais deixa as simulações otimistas": não deixa.
- "Limiar de 80% escolhido por uma noite só": o 80% ganha no mercado eficiente.
- "A ordem de chegada simulada é menos informativa e piora o modelo": não piora entre 2% e 35% apurado.
- "Calibrar dentro da amostra infla os resultados": trocar a calibração quase não muda nada.
- "Vender a mercado custou 2–3¢": era efeito da série por minuto. O custo real foi de ~1¢, e ~0,5¢ nos minutos das vendas.

---

## 4. Checklist do dia 25 (horário de Brasília; no relógio deste PC, 1 h a menos)

**Até 16h40:**
1. Feche os painéis e monitores de ensaio, ou reinicie o PC. `netstat -ano | findstr :8050` tem de voltar vazio.
2. Deixe o PC na tomada, com a tampa aberta e a bateria configurada para não suspender. Deixe a rede de reserva pronta.
3. Faça o pré-voo só de leitura, sem abrir sessão:
   - `br-c0001-e006258-u.json` responde, com ele=6258, t=2 e data 25/10;
   - os candidatos aparecem como "22" e "13" em texto;
   - as 28 UFs respondem;
   - a Polymarket mostra bid/ask nas 8 faixas.

**Entre 16h50 e 16h55:**

4. Rode `python eleicao/painel.py --ao-vivo --faixa "<sua faixa>" --degrau f90@2:100`, com o degrau sem espaços.
5. Em `http://127.0.0.1:8050/api/config` e no topo da página, confira:
   - a sua faixa, o lado Sim e o plano `f90@2:100` "aguardando";
   - a aba ao vivo "rodando", lendo resultados.tse.jus.br.
6. Ligue o Som e ouça o bipe de teste. Deixe a janela visível.
7. Compare as suas cotas com "Cotas no bid".

**Depois das 17h05:**

8. A "parcial (TSE)" tem de deixar de mostrar "—".
9. Seções% e eleitorado% devem subir juntos, e a fila não pode crescer sem parar.
10. A Polymarket deve ter sido atualizada há menos de 30 s.
11. Se o eleitorado parar enquanto as seções sobem, ou se o PC tiver dormido, não aja por disparo até os dois voltarem a andar juntos e a fila cair a poucas centenas.
12. Se "erro no ciclo" se repetir por mais de 5 min, acompanhe pelo site do TSE e pela Polymarket. Se o painel cair, use `--retomar ultima`.

**Quando o PLANO apitar:**

13. Venda logo: meta de até 5 min, limite de uns 10. A venda é manual. Anote a hora do aviso e a hora da venda.
14. Se o disparo vier tarde (depois de ~60% apurado) com a margem prevista a menos de 0,4 de 4, a venda vale só 3 a 6¢ por cota, e segurar custa pouco (até ~US$ 0,73 por US$ 100 em média). A escolha é sua.
15. No fim, se a margem pelos votos ficar a menos de 0,01 de 4, não trate a faixa como certa, por causa do arredondamento do TSE. O pagamento sai horas depois, na resolução do UMA (o sistema de resolução da Polymarket).

---

## 5. Limites do que foi testado

- **Só uma noite com preço real** (4/10, 1º turno, faixas de 5 pontos), e o mercado demorou um tempo específico para reagir naquela noite.
- **Só um 2º turno real com hora de chegada das seções** (2022), e foi a noite usada para desenhar o modelo.
- **As simulações são o melhor caso.** O gerador tem a mesma estrutura do modelo, e o erro sistemático do 1º turno de 2026 não aparece nelas.
- **O mercado simulado segue o próprio modelo.** O ritmo foi ajustado numa noite só e não separa "reagir devagar" de "esperar informação".
- **A cobertura de margens foi completada por aproximação.** Faltavam vitórias de Lula por mais de 1 ponto e de Flávio acima de 10; elas foram cobertas com noites extras ou deslocadas.
- **Spread e profundidade do livro durante a apuração não foram medidos**, porque o histórico não tem bid/ask.
- **Não testado:**
  - outro 2º turno real;
  - mudança de voto ligada ao tamanho do município ou à hora;
  - uma UF grande atrasada mais de 30 min;
  - um ritmo nacional muito diferente;
  - o comportamento do TSE no pico de 25/10.
- **As três investigações finais não passaram pelos céticos:** noites de fronteira com votos reais, grade de arrependimento e atraso real. As alternativas 10@2, 20@2 e o piso de 15¢ foram avaliadas nos mesmos dados em que surgiram, e não há teste pré-registrado.
- **O trade é só simulação.** Do Brasil, a conta só permite vender.

Os scripts e dados dos testes estão em `C:\Users\lucas\AppData\Local\Temp\claude\C--Users-lucas-Documents-Projects-bot-perps\76451049-7309-49f5-9b71-e4a3ee092b99\scratchpad\wf_*`. Nenhum arquivo do projeto foi editado.

---

Gerado em 16/10/2026 por uma bateria de 109 agentes (8 testes/auditorias, 2 céticos por achado médio/alto, crítico de completude com 3 lacunas). A pasta do scratchpad é temporária: copie os scripts que quiser guardar.
