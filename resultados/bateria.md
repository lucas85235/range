# Bateria de testes das estratégias

Gerado por `estudos/bateria.py`. Todas começam com US$100; posição comprada ao preço de hoje (F <4% a 40,5¢, F 4-8% a 32,5¢). Média, mediana e prejuízo pesam cada noite pela chance que o mercado dá hoje ao cenário dela. Mercados: os três ritmos (o preço vai atrás do modelo) e um que sabe mais que o modelo (metade do erro dele, sem atraso).

## 0. O que o mercado seguiu na noite real do 1º turno (4/10)

Erro médio do preço de cada faixa, minuto a minuto, de 17h a 21h: **segue a parcial 10.3¢** (melhor ajuste: ruído k = 4.0); **vai atrás do modelo 2.9¢** (começa 30 min depois das 17h, τ = 35 min); a melhor mistura das duas é 10% parcial + 90% modelo (2.7¢). A parcial mostrou Flávio +10 por duas horas; quem a lesse assim levaria o preço para "F 5-10%". O mercado foi para a faixa certa, só que 30 a 60 minutos depois do modelo.

| trecho | segue a parcial | vai atrás do modelo | preço parado (de antes) |
|---|---|---|---|
| 17h00–17h30 | 3.6¢ | 1.7¢ | 1.9¢ |
| 17h30–18h00 | 12.1¢ | 3.8¢ | 16.4¢ |
| 18h00–19h00 | 12.9¢ | 4.8¢ | 27.2¢ |
| 19h00–21h00 | 9.2¢ | 0.8¢ | 33.4¢ |

| hora | apurado | parcial do TSE | "F <5%" no mercado | se seguisse a parcial | se fosse atrás do modelo | modelo |
|---|---|---|---|---|---|---|
| 17h15 | 1% | F +2.5 | 31% | 32% | 29% | 63% |
| 17h30 | 2% | F +7.5 | 34% | 33% | 38% | 96% |
| 17h45 | 7% | F +9.8 | 67% | 37% | 59% | 97% |
| 18h00 | 14% | F +10.4 | 71% | 44% | 72% | 97% |
| 18h30 | 34% | F +9.4 | 81% | 58% | 89% | 100% |
| 19h00 | 59% | F +7.6 | 93% | 65% | 95% | 100% |

## 1. Resultado por mercado — começando em Sim "F <4%"

| mercado | estratégia | média | mediana | 10% piores | prejuízo | perde > metade | operou |
|---|---|---|---|---|---|---|---|
| como em 4/10 | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 61% | 61% | 0% |
| como em 4/10 | Chance ≤ 20% (desde 5%) | US$ 151 | US$ 98 | US$ 90 | 62% | 1% | 62% |
| como em 4/10 | Chance ≤ 20% (desde 20%) | US$ 125 | US$ 56 | US$ 41 | 62% | 41% | 62% |
| como em 4/10 | Faixa de 90% sai da sua | US$ 137 | US$ 98 | US$ 24 | 62% | 25% | 62% |
| como em 4/10 | Escalonada | US$ 144 | US$ 98 | US$ 60 | 62% | 2% | 64% |
| como em 4/10 | Stop no preço (vende se o preço < 15¢) | US$ 115 | US$ 33 | US$ 31 | 61% | 61% | 61% |
| como em 4/10 | Trade com posição | US$ 344 | US$ 291 | US$ 158 | 7% | 2% | 65% |
| como em 4/10 | Trade em dinheiro | US$ 349 | US$ 299 | US$ 164 | 6% | 0% | 99% |
| mais esperto | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 61% | 61% | 0% |
| mais esperto | Chance ≤ 20% (desde 5%) | US$ 117 | US$ 53 | US$ 26 | 62% | 46% | 62% |
| mais esperto | Chance ≤ 20% (desde 20%) | US$ 106 | US$ 40 | US$ 3 | 62% | 62% | 62% |
| mais esperto | Faixa de 90% sai da sua | US$ 114 | US$ 53 | US$ 10 | 62% | 49% | 62% |
| mais esperto | Escalonada | US$ 112 | US$ 36 | US$ 26 | 62% | 62% | 64% |
| mais esperto | Stop no preço (vende se o preço < 15¢) | US$ 114 | US$ 34 | US$ 30 | 62% | 62% | 62% |
| mais esperto | Trade com posição | US$ 151 | US$ 134 | US$ 48 | 34% | 11% | 65% |
| mais esperto | Trade em dinheiro | US$ 159 | US$ 166 | US$ 100 | 10% | 4% | 94% |
| igual ao modelo | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 61% | 61% | 0% |
| igual ao modelo | Chance ≤ 20% (desde 5%) | US$ 104 | US$ 40 | US$ 0 | 62% | 62% | 62% |
| igual ao modelo | Chance ≤ 20% (desde 20%) | US$ 104 | US$ 38 | US$ 0 | 62% | 62% | 62% |
| igual ao modelo | Faixa de 90% sai da sua | US$ 98 | US$ 9 | US$ 0 | 62% | 62% | 62% |
| igual ao modelo | Escalonada | US$ 101 | US$ 31 | US$ 0 | 62% | 62% | 64% |
| igual ao modelo | Stop no preço (vende se o preço < 15¢) | US$ 98 | US$ 33 | US$ 6 | 66% | 66% | 66% |
| igual ao modelo | Trade com posição | US$ 104 | US$ 61 | US$ 0 | 65% | 46% | 65% |
| igual ao modelo | Trade em dinheiro | US$ 100 | US$ 100 | US$ 100 | 0% | 0% | 0% |
| sabe mais que o modelo | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 61% | 61% | 0% |
| sabe mais que o modelo | Chance ≤ 20% (desde 5%) | US$ 106 | US$ 39 | US$ 0 | 62% | 54% | 62% |
| sabe mais que o modelo | Chance ≤ 20% (desde 20%) | US$ 104 | US$ 32 | US$ 0 | 62% | 57% | 62% |
| sabe mais que o modelo | Faixa de 90% sai da sua | US$ 99 | US$ 13 | US$ 0 | 62% | 62% | 62% |
| sabe mais que o modelo | Escalonada | US$ 102 | US$ 31 | US$ 0 | 62% | 61% | 64% |
| sabe mais que o modelo | Stop no preço (vende se o preço < 15¢) | US$ 110 | US$ 33 | US$ 11 | 61% | 61% | 61% |
| sabe mais que o modelo | Trade com posição | US$ 105 | US$ 56 | US$ 0 | 65% | 48% | 65% |
| sabe mais que o modelo | Trade em dinheiro | US$ 99 | US$ 100 | US$ 64 | 12% | 9% | 31% |
| segue a parcial do TSE | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 61% | 61% | 0% |
| segue a parcial do TSE | Chance ≤ 20% (desde 5%) | US$ 146 | US$ 88 | US$ 83 | 62% | 1% | 62% |
| segue a parcial do TSE | Chance ≤ 20% (desde 20%) | US$ 143 | US$ 95 | US$ 67 | 62% | 1% | 62% |
| segue a parcial do TSE | Faixa de 90% sai da sua | US$ 148 | US$ 99 | US$ 84 | 52% | 3% | 62% |
| segue a parcial do TSE | Escalonada | US$ 146 | US$ 92 | US$ 83 | 62% | 1% | 64% |
| segue a parcial do TSE | Stop no preço (vende se o preço < 15¢) | US$ 112 | US$ 34 | US$ 32 | 63% | 63% | 63% |
| segue a parcial do TSE | Trade com posição | US$ 332 | US$ 263 | US$ 247 | 1% | 1% | 65% |
| segue a parcial do TSE | Trade em dinheiro | US$ 382 | US$ 306 | US$ 266 | 0% | 0% | 100% |

## 1. Resultado por mercado — começando em Sim "F 4-8%"

| mercado | estratégia | média | mediana | 10% piores | prejuízo | perde > metade | operou |
|---|---|---|---|---|---|---|---|
| como em 4/10 | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 69% | 69% | 0% |
| como em 4/10 | Chance ≤ 20% (desde 5%) | US$ 155 | US$ 97 | US$ 68 | 70% | 1% | 70% |
| como em 4/10 | Chance ≤ 20% (desde 20%) | US$ 126 | US$ 49 | US$ 38 | 69% | 51% | 69% |
| como em 4/10 | Faixa de 90% sai da sua | US$ 150 | US$ 97 | US$ 21 | 69% | 16% | 69% |
| como em 4/10 | Escalonada | US$ 153 | US$ 97 | US$ 57 | 69% | 6% | 71% |
| como em 4/10 | Stop no preço (vende se o preço < 15¢) | US$ 123 | US$ 41 | US$ 40 | 69% | 69% | 69% |
| como em 4/10 | Trade com posição | US$ 346 | US$ 308 | US$ 167 | 5% | 0% | 74% |
| como em 4/10 | Trade em dinheiro | US$ 349 | US$ 299 | US$ 164 | 6% | 0% | 99% |
| mais esperto | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 69% | 69% | 0% |
| mais esperto | Chance ≤ 20% (desde 5%) | US$ 116 | US$ 35 | US$ 22 | 70% | 55% | 70% |
| mais esperto | Chance ≤ 20% (desde 20%) | US$ 104 | US$ 8 | US$ 1 | 69% | 60% | 69% |
| mais esperto | Faixa de 90% sai da sua | US$ 122 | US$ 48 | US$ 12 | 69% | 52% | 69% |
| mais esperto | Escalonada | US$ 115 | US$ 34 | US$ 22 | 69% | 67% | 71% |
| mais esperto | Stop no preço (vende se o preço < 15¢) | US$ 123 | US$ 41 | US$ 38 | 69% | 69% | 69% |
| mais esperto | Trade com posição | US$ 146 | US$ 94 | US$ 61 | 60% | 4% | 74% |
| mais esperto | Trade em dinheiro | US$ 159 | US$ 166 | US$ 100 | 10% | 4% | 94% |
| igual ao modelo | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 69% | 69% | 0% |
| igual ao modelo | Chance ≤ 20% (desde 5%) | US$ 103 | US$ 9 | US$ 0 | 70% | 57% | 70% |
| igual ao modelo | Chance ≤ 20% (desde 20%) | US$ 102 | US$ 2 | US$ 0 | 69% | 61% | 69% |
| igual ao modelo | Faixa de 90% sai da sua | US$ 99 | US$ 10 | US$ 0 | 69% | 69% | 69% |
| igual ao modelo | Escalonada | US$ 102 | US$ 9 | US$ 0 | 69% | 69% | 71% |
| igual ao modelo | Stop no preço (vende se o preço < 15¢) | US$ 107 | US$ 40 | US$ 6 | 71% | 71% | 71% |
| igual ao modelo | Trade com posição | US$ 101 | US$ 43 | US$ 0 | 74% | 52% | 74% |
| igual ao modelo | Trade em dinheiro | US$ 100 | US$ 100 | US$ 100 | 0% | 0% | 0% |
| sabe mais que o modelo | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 69% | 69% | 0% |
| sabe mais que o modelo | Chance ≤ 20% (desde 5%) | US$ 103 | US$ 9 | US$ 0 | 69% | 62% | 70% |
| sabe mais que o modelo | Chance ≤ 20% (desde 20%) | US$ 102 | US$ 3 | US$ 0 | 69% | 62% | 69% |
| sabe mais que o modelo | Faixa de 90% sai da sua | US$ 99 | US$ 7 | US$ 0 | 69% | 69% | 69% |
| sabe mais que o modelo | Escalonada | US$ 102 | US$ 9 | US$ 0 | 69% | 64% | 71% |
| sabe mais que o modelo | Stop no preço (vende se o preço < 15¢) | US$ 116 | US$ 39 | US$ 20 | 69% | 69% | 69% |
| sabe mais que o modelo | Trade com posição | US$ 100 | US$ 27 | US$ 0 | 69% | 59% | 74% |
| sabe mais que o modelo | Trade em dinheiro | US$ 99 | US$ 100 | US$ 64 | 12% | 9% | 31% |
| segue a parcial do TSE | Segurar até o fim | US$ 95 | US$ 0 | US$ 0 | 69% | 69% | 0% |
| segue a parcial do TSE | Chance ≤ 20% (desde 5%) | US$ 165 | US$ 99 | US$ 92 | 54% | 0% | 70% |
| segue a parcial do TSE | Chance ≤ 20% (desde 20%) | US$ 172 | US$ 116 | US$ 95 | 18% | 0% | 69% |
| segue a parcial do TSE | Faixa de 90% sai da sua | US$ 167 | US$ 95 | US$ 90 | 52% | 1% | 69% |
| segue a parcial do TSE | Escalonada | US$ 165 | US$ 100 | US$ 92 | 51% | 0% | 71% |
| segue a parcial do TSE | Stop no preço (vende se o preço < 15¢) | US$ 117 | US$ 41 | US$ 36 | 71% | 71% | 67% |
| segue a parcial do TSE | Trade com posição | US$ 364 | US$ 308 | US$ 243 | 2% | 1% | 74% |
| segue a parcial do TSE | Trade em dinheiro | US$ 382 | US$ 306 | US$ 266 | 0% | 0% | 100% |

## 2. Por cenário (mercado "mais esperto", Sim "F <4%")

| cenário | noites | Segurar até o fim | Chance ≤ 20% (desde 5%) | Chance ≤ 20% (desde 20%) | Faixa de 90% sai da sua | Escalonada | Stop no preço (vende se o preço < 15¢) | Trade com posição | Trade em dinheiro |
|---|---|---|---|---|---|---|---|---|---|
| Lula vence | 5 | US$ 0 | US$ 48 | US$ 30 | US$ 14 | US$ 35 | US$ 34 | US$ 145 | US$ 195 |
| F <4%, longe de 4 (0 a 3) | 21 | US$ 247 | US$ 247 | US$ 247 | US$ 247 | US$ 244 | US$ 247 | US$ 239 | US$ 151 |
| F <4%, perto de 4 (3 a 4) | 29 | US$ 247 | US$ 233 | US$ 239 | US$ 240 | US$ 231 | US$ 239 | US$ 199 | US$ 125 |
| F 4-8%, perto de 4 (4 a 5) | 18 | US$ 0 | US$ 46 | US$ 33 | US$ 18 | US$ 36 | US$ 30 | US$ 97 | US$ 141 |
| F 4-8%, longe de 4 (5 a 8) | 15 | US$ 0 | US$ 30 | US$ 10 | US$ 43 | US$ 28 | US$ 31 | US$ 79 | US$ 155 |
| Flávio por 8 ou mais | 12 | US$ 0 | US$ 24 | US$ 3 | US$ 49 | US$ 24 | US$ 33 | US$ 71 | US$ 169 |

## 3. Viés do modelo por fase da apuração

Erro = margem prevista − resultado (> 0: puxa para Flávio). |z| > 1,64 deveria acontecer ~10% das vezes se a incerteza estiver certa.

| apuração | apurado | erro médio (pp) | erro típico (pp) | puxa para F | |z| > 1,64 |
|---|---|---|---|---|---|
| simulações | 0–2% | 0.63 | 1.53 | 74% | 6% |
| simulações | 2–5% | 0.29 | 0.8 | 64% | 4% |
| simulações | 5–10% | 0.05 | 0.64 | 54% | 3% |
| simulações | 10–20% | -0.04 | 0.63 | 50% | 6% |
| simulações | 20–35% | -0.12 | 0.46 | 39% | 4% |
| simulações | 35–50% | -0.09 | 0.19 | 34% | 0% |
| simulações | 50–70% | -0.02 | 0.08 | 36% | 0% |
| simulações | 70–90% | -0.01 | 0.04 | 36% | 0% |
| simulações | 90–100% | -0 | 0.01 | 35% | 20% |
| 2º turno de 2022 | 0–2% | -0.45 | 1.37 | 44% | 0% |
| 2º turno de 2022 | 2–5% | -0.21 | 0.34 | 29% | 0% |
| 2º turno de 2022 | 5–10% | 0.02 | 0.19 | 56% | 0% |
| 2º turno de 2022 | 10–20% | -0.27 | 0.28 | 0% | 0% |
| 2º turno de 2022 | 20–35% | -0.06 | 0.21 | 48% | 0% |
| 2º turno de 2022 | 35–50% | 0.26 | 0.26 | 100% | 0% |
| 2º turno de 2022 | 50–70% | 0.21 | 0.22 | 100% | 0% |
| 2º turno de 2022 | 70–90% | 0.02 | 0.05 | 50% | 0% |
| 2º turno de 2022 | 90–100% | -0.01 | 0.01 | 38% | 14% |
| 1º turno de 2026 | 0–2% | -2.33 | 3.86 | 32% | 5% |
| 1º turno de 2026 | 2–5% | 1.83 | 1.97 | 100% | 33% |
| 1º turno de 2026 | 5–10% | 1.97 | 1.97 | 100% | 100% |
| 1º turno de 2026 | 10–20% | 2.22 | 2.22 | 100% | 100% |
| 1º turno de 2026 | 20–35% | 1.9 | 1.9 | 100% | 100% |
| 1º turno de 2026 | 35–50% | 1.36 | 1.37 | 100% | 100% |
| 1º turno de 2026 | 50–70% | 0.99 | 1 | 100% | 100% |
| 1º turno de 2026 | 70–90% | 0.44 | 0.45 | 100% | 100% |
| 1º turno de 2026 | 90–100% | 0.26 | 0.27 | 100% | 100% |

## 4. Para que lado as estratégias erram (mercado "mais esperto", Sim "F <4%")

| estratégia | resultado | noites |
|---|---|---|
| Segurar até o fim | segurou e perdeu | 61% |
| Segurar até o fim | segurou e ganhou | 39% |
| Chance ≤ 20% (desde 5%) | vendeu e a faixa perdeu | 61% |
| Chance ≤ 20% (desde 5%) | segurou e ganhou | 38% |
| Chance ≤ 20% (desde 5%) | vendeu à toa (modelo puxava para F) | 1% |
| Chance ≤ 20% (desde 20%) | vendeu e a faixa perdeu | 61% |
| Chance ≤ 20% (desde 20%) | segurou e ganhou | 38% |
| Chance ≤ 20% (desde 20%) | vendeu à toa (modelo puxava para F) | 0% |
| Faixa de 90% sai da sua | vendeu e a faixa perdeu | 61% |
| Faixa de 90% sai da sua | segurou e ganhou | 38% |
| Faixa de 90% sai da sua | vendeu à toa (modelo puxava para F) | 0% |
| Escalonada | vendeu e a faixa perdeu | 61% |
| Escalonada | segurou e ganhou | 36% |
| Escalonada | vendeu à toa (modelo puxava para F) | 1% |
| Escalonada | vendeu à toa (modelo puxava para L) | 1% |
| Stop no preço (vende se o preço < 15¢) | vendeu e a faixa perdeu | 61% |
| Stop no preço (vende se o preço < 15¢) | segurou e ganhou | 38% |
| Stop no preço (vende se o preço < 15¢) | vendeu à toa (modelo puxava para F) | 0% |
| Trade com posição | terminou em dinheiro | 10% |
| Trade com posição | faixa certa | 90% |
| Trade em dinheiro | não comprou | 6% |
| Trade em dinheiro | faixa certa | 86% |
| Trade em dinheiro | errou para Flávio | 4% |
| Trade em dinheiro | errou para Lula | 4% |

## 5. Peso dos cenários (mercado "mais esperto", Sim "F <4%")

| peso | estratégia | média | mediana | prejuízo |
|---|---|---|---|---|
| chances de hoje | Trade em dinheiro | US$ 159 | US$ 166 | 10% |
| chances de hoje | Trade com posição | US$ 151 | US$ 134 | 34% |
| chances de hoje | Chance ≤ 20% (desde 5%) | US$ 117 | US$ 53 | 62% |
| chances de hoje | Stop no preço (vende se o preço < 15¢) | US$ 114 | US$ 34 | 62% |
| chances de hoje | Faixa de 90% sai da sua | US$ 114 | US$ 53 | 62% |
| chances de hoje | Escalonada | US$ 112 | US$ 36 | 62% |
| chances de hoje | Chance ≤ 20% (desde 20%) | US$ 106 | US$ 40 | 62% |
| chances de hoje | Segurar até o fim | US$ 95 | US$ 0 | 61% |
| todas as noites iguais | Trade com posição | US$ 153 | US$ 131 | 39% |
| todas as noites iguais | Trade em dinheiro | US$ 147 | US$ 158 | 15% |
| todas as noites iguais | Faixa de 90% sai da sua | US$ 138 | US$ 61 | 51% |
| todas as noites iguais | Chance ≤ 20% (desde 5%) | US$ 138 | US$ 58 | 52% |
| todas as noites iguais | Stop no preço (vende se o preço < 15¢) | US$ 137 | US$ 35 | 51% |
| todas as noites iguais | Escalonada | US$ 134 | US$ 42 | 51% |
| todas as noites iguais | Chance ≤ 20% (desde 20%) | US$ 130 | US$ 47 | 51% |
| todas as noites iguais | Segurar até o fim | US$ 123 | US$ 0 | 50% |

## 6. Parâmetros do trade: dentro × fora da amostra (mercado "mais esperto")

| variante | escolhida em | parâmetros | média dentro | média fora | padrão dentro | padrão fora |
|---|---|---|---|---|---|---|
| Trade com posição | A | limiar 60%, vantagem 0 pts, desde 2%, 1 troca(s) | US$ 158 | US$ 168 | US$ 150 | US$ 153 |
| Trade com posição | B | limiar 60%, vantagem 0 pts, desde 2%, 2 troca(s) | US$ 173 | US$ 157 | US$ 153 | US$ 150 |
| Trade em dinheiro | A | limiar 60%, vantagem 5 pts, desde 2%, 1 troca(s) | US$ 174 | US$ 178 | US$ 162 | US$ 159 |
| Trade em dinheiro | B | limiar 60%, vantagem 0 pts, desde 2%, 2 troca(s) | US$ 180 | US$ 173 | US$ 159 | US$ 162 |

## 7. Apurações reais, com preço simulado (começando em Sim "F <4%")

Resultados: 2º turno de 2022: L <4% (F -1.8), 1º turno de 2026: F <4% (F +2.0).

| apuração | estratégia | como em 4/10 | mais esperto | igual ao modelo | sabe mais que o modelo | segue a parcial do TSE |
|---|---|---|---|---|---|---|
| 2º turno de 2022 | Segurar até o fim | US$ 0 | US$ 0 | US$ 0 | US$ 0 | US$ 0 |
| 2º turno de 2022 | Chance ≤ 20% (desde 5%) | US$ 98 | US$ 35 | US$ 12 | US$ 8 | US$ 87 |
| 2º turno de 2022 | Chance ≤ 20% (desde 20%) | US$ 43 | US$ 4 | US$ 0 | US$ 0 | US$ 96 |
| 2º turno de 2022 | Faixa de 90% sai da sua | US$ 98 | US$ 44 | US$ 5 | US$ 8 | US$ 86 |
| 2º turno de 2022 | Escalonada | US$ 97 | US$ 33 | US$ 10 | US$ 7 | US$ 88 |
| 2º turno de 2022 | Stop no preço (vende se o preço < 15¢) | US$ 34 | US$ 34 | US$ 21 | US$ 29 | US$ 34 |
| 2º turno de 2022 | Trade com posição | US$ 500 | US$ 73 | US$ 5 | US$ 8 | US$ 487 |
| 2º turno de 2022 | Trade em dinheiro | US$ 513 | US$ 168 | US$ 100 | US$ 100 | US$ 565 |
| 1º turno de 2026 | Segurar até o fim | US$ 247 | US$ 247 | US$ 247 | US$ 247 | US$ 247 |
| 1º turno de 2026 | Chance ≤ 20% (desde 5%) | US$ 247 | US$ 247 | US$ 247 | US$ 247 | US$ 247 |
| 1º turno de 2026 | Chance ≤ 20% (desde 20%) | US$ 247 | US$ 247 | US$ 247 | US$ 247 | US$ 247 |
| 1º turno de 2026 | Faixa de 90% sai da sua | US$ 247 | US$ 247 | US$ 247 | US$ 247 | US$ 247 |
| 1º turno de 2026 | Escalonada | US$ 188 | US$ 186 | US$ 185 | US$ 238 | US$ 191 |
| 1º turno de 2026 | Stop no preço (vende se o preço < 15¢) | US$ 247 | US$ 247 | US$ 2 | US$ 31 | US$ 247 |
| 1º turno de 2026 | Trade com posição | US$ 46 | US$ 69 | US$ 65 | US$ 1 | US$ 428 |
| 1º turno de 2026 | Trade em dinheiro | US$ 54 | US$ 100 | US$ 100 | US$ 0 | US$ 496 |

### Noite real do 1º turno com os preços reais da Polymarket (faixas de 5 pontos)

| posição | estratégia | valor | o que fez |
|---|---|---|---|
| F <5% (ganhou) | Segurar até o fim | US$ 368 | não vendeu |
| F <5% (ganhou) | Chance ≤ 20% (desde 5%) | US$ 368 | não vendeu |
| F <5% (ganhou) | Chance ≤ 20% (desde 20%) | US$ 368 | não vendeu |
| F <5% (ganhou) | Faixa de 90% sai da sua | US$ 368 | não vendeu |
| F <5% (ganhou) | Escalonada | US$ 368 | não vendeu |
| F <5% (ganhou) | Stop no preço (vende se o preço < 15¢) | US$ 368 | não vendeu |
| L <5% (perdeu) | Segurar até o fim | US$ 0 | não vendeu |
| L <5% (perdeu) | Chance ≤ 20% (desde 5%) | US$ 47 | vendeu às 17h45 a 27¢ |
| L <5% (perdeu) | Chance ≤ 20% (desde 20%) | US$ 20 | vendeu às 18h20 a 12¢ |
| L <5% (perdeu) | Faixa de 90% sai da sua | US$ 84 | vendeu às 17h33 a 50¢ |
| L <5% (perdeu) | Escalonada | US$ 47 | vendeu às 17h45 a 27¢ |
| L <5% (perdeu) | Stop no preço (vende se o preço < 15¢) | US$ 23 | vendeu às 17h57 a 13¢ |

| estratégia | começa em | valor | o que fez |
|---|---|---|---|
| Trade com posição | F <5% | US$ 368 | não operou |
| Trade com posição | L <5% | US$ 209 | vende L <5% a 50¢; compra F <5% a 40¢ |
| Trade em dinheiro | dinheiro | US$ 250 | compra F <5% a 40¢ |

## 8. Limiar de confiança do trade × o viés pró-Flávio

No 1º turno de 2026 o modelo ficou ~2 pontos pró-Flávio por horas (seção 3). Com limiar baixo, o trade compra "F 4-8%" nesse erro; com limiar mais alto, ele espera. Começando em Sim "F <4%" (com posição) ou em dinheiro.

| variante | limiar | simulações, como em 4/10 | simulações, mais esperto | simulações, sabe mais que o modelo | simulações, segue a parcial do TSE | 2º turno de 2022, mais esperto | 1º turno de 2026, como em 4/10 | 1º turno de 2026, sabe mais que o modelo |
|---|---|---|---|---|---|---|---|---|
| Trade em dinheiro | 60% | US$ 354 (3% prejuízo) | US$ 175 (11% prejuízo) | US$ 98 (14% prejuízo) | US$ 380 (1% prejuízo) | US$ 168 | US$ 71 | US$ 8 |
| Trade em dinheiro | 70% | US$ 349 (6% prejuízo) | US$ 159 (10% prejuízo) | US$ 99 (12% prejuízo) | US$ 382 (0% prejuízo) | US$ 168 | US$ 54 | US$ 0 |
| Trade em dinheiro | 80% | US$ 312 (3% prejuízo) | US$ 143 (5% prejuízo) | US$ 103 (5% prejuízo) | US$ 380 (0% prejuízo) | US$ 168 | US$ 100 | US$ 100 |
| Trade em dinheiro | 90% | US$ 222 (1% prejuízo) | US$ 118 (1% prejuízo) | US$ 102 (1% prejuízo) | US$ 417 (0% prejuízo) | US$ 158 | US$ 100 | US$ 100 |
| Trade com posição | 60% | US$ 347 (4% prejuízo) | US$ 163 (31% prejuízo) | US$ 105 (65% prejuízo) | US$ 329 (3% prejuízo) | US$ 73 | US$ 76 | US$ 14 |
| Trade com posição | 70% | US$ 344 (7% prejuízo) | US$ 151 (34% prejuízo) | US$ 105 (65% prejuízo) | US$ 332 (1% prejuízo) | US$ 73 | US$ 46 | US$ 1 |
| Trade com posição | 80% | US$ 303 (12% prejuízo) | US$ 135 (53% prejuízo) | US$ 107 (62% prejuízo) | US$ 323 (6% prejuízo) | US$ 73 | US$ 247 | US$ 247 |
| Trade com posição | 90% | US$ 210 (32% prejuízo) | US$ 112 (62% prejuízo) | US$ 102 (62% prejuízo) | US$ 357 (9% prejuízo) | US$ 67 | US$ 247 | US$ 247 |
