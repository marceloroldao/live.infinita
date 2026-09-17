# Visual System 001 — Live Infinita

## Direção

A Live deixa de parecer um painel de diagnóstico e passa a parecer um pequeno mundo narrativo em transmissão. A linguagem é **storybook + diorama**: formas simples, profundidade por camadas, movimento atmosférico discreto e HUD secundário ao mundo.

## Hierarquia visual

1. **Mundo** — ocupa a maior área e deve continuar legível mesmo sem HUD.
2. **Narrativa** — aparece como legenda editorial na base da cena.
3. **Audiência** — surge de forma temporária e translúcida no canto superior direito.
4. **Marca / estado LIVE** — identificação curta, sempre presente, sem competir com a cena.
5. **Telemetria técnica** — reduzida a uma linha discreta na borda inferior.

## Cenário procedural

O renderer desenha céu, luz, horizonte, colinas e primeiro plano sem assets externos. O período do World State determina paleta diurna/noturna.

- Dia: céu claro em bandas, sol, nuvens lentas, vegetação mais luminosa.
- Noite: céu profundo, estrelas com cintilação, lua, terreno de baixo contraste.
- Primeiro plano: camada escura em formato de diorama para aumentar profundidade.
- Vinheta: bordas sutis para centralizar o olhar.

## Entidades

As entidades continuam derivadas exclusivamente do World State, mas ganham linguagem ilustrada:

- árvores com copa em massas sobrepostas, tronco modelado e sombra;
- fogueira com lenha, halo de luz e chama procedural pulsante;
- personagens com silhueta, volume, sombra e movimento interpolado;
- entidades desconhecidas permanecem representáveis por fallback visual.

## Movimento

Movimento deve comunicar vida sem parecer interface animada:

- entidades interpolam suavemente para nova posição;
- fogo pulsa continuamente quando aceso;
- estrelas cintilam;
- nuvens derivam lentamente;
- nenhum movimento altera o World State.

## HUD de broadcast

- canto superior esquerdo: `LIVE INFINITA` + assinatura `um mundo que continua`;
- canto superior direito: selo `AO VIVO`;
- feed de audiência aparece somente quando há eventos recentes;
- narrativa ocupa cartão central inferior;
- conexão/ação/seq ficam em linha técnica discreta no rodapé.

## Invariantes

- Renderer nunca é autoridade do mundo.
- Animações são puramente visuais.
- Ausência de assets externos preserva deploy leve e determinístico.
- A cena deve funcionar em Web e no renderer Godot nativo server-side.
- A camada visual deve continuar validável pelo smoke test Xvfb + FFmpeg do CI.

## Próximas evoluções visuais

Após validar esta baseline em 1280×720:

1. câmera virtual com enquadramento suave por evento;
2. partículas leves (brasas, poeira, chuva/neve conforme ambiente);
3. sistema de biomas e paletas derivado do World State;
4. personagens com sprites/rig somente quando a ontologia visual estiver estabilizada;
5. transições cinematográficas entre estados importantes;
6. composição vertical 9:16 dedicada ao TikTok, sem simplesmente cortar o 16:9.
