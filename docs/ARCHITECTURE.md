# Arquitetura — Live Infinita

## Regra de autoridade

A única autoridade persistente é o **World Runtime + WorldStore**. A Memoria.ia será um backend de persistência por adapter, não uma dependência acoplada diretamente ao domínio.

- Chat propõe intenções.
- LLM interpreta e narra.
- Runtime valida.
- WorldStore persiste o estado aceito.
- Memoria.ia entra através de `MemoriaIaWorldStore`.
- Renderer apenas projeta o estado.

## Fluxo crítico atual

```text
Live Adapter -> Event Gateway -> Filter/Aggregator -> Intent
-> Proposed Action -> World Runtime -> Delta -> WorldStore
-> renderer-godot + narration/Piper -> OBS

Admin Web <- estado / métricas / preview <- Runtime + Renderer
```

## Serviços

### gateway
Normaliza eventos externos em `LiveEvent` e suporta TikTok, YouTube e Simulator.

### world-runtime
Mantém o estado autoritativo, aplica regras, valida `ProposedAction`, gera `Delta`, eventos e versões. Deve ter um único escritor autoritativo no MVP.

### world-store
Contrato de persistência independente do backend. O MVP deve suportar pelo menos:

- `LocalWorldStore`: permite implementar e testar sem depender da refatoração da Memoria.ia.
- `MemoriaIaWorldStore`: adapter futuro/parallel para persistir o mesmo domínio na Memoria.ia.

A troca entre stores não pode exigir mudanças no World Runtime.

### ai-router
Abstrai provedores de inferência. No início pode usar OpenAI apenas quando necessário. Deve permitir substituição por modelos locais sem alterar contratos do domínio.

### narration
No início existe uma única voz de narrador. A baseline deve ser TTS local com Piper, usando templates determinísticos no MVP-001 e LLM opcional em marcos posteriores. Personagens não precisam de voz própria inicialmente.

### renderer-godot
Godot 4 é o renderer principal. O renderer recebe `WorldSnapshot` e `WorldDelta` e mantém um espelho visual por `entity_id`. O visual inicial deve ser 2D/2.5D procedural, sem exigir imagens pré-renderizadas como fonte de verdade.

### admin-web
Painel remoto em HTML/CSS/JS para observar o servidor sem exigir desktop Linux completo. Deve mostrar:

- World State atual;
- versão atual;
- eventos e deltas recentes;
- ações aceitas/rejeitadas;
- status do renderer;
- status do TTS;
- métricas e erros;
- preview do mundo em baixa resolução/FPS.

O preview é apenas observabilidade; ele não é autoridade sobre o mundo.

### stream-output
Saída inicial recomendada: `Godot nativo -> OBS -> plataforma`. Evoluções futuras podem usar Spout, NDI, FFmpeg, GStreamer, RTMP ou SRT sem alterar World State ou contratos de domínio.

## Linux e renderização

O backend deve poder rodar em Linux sem GNOME/KDE. Memoria.ia, World Runtime, gateway, stores, TTS e admin API devem funcionar headless.

A camada de renderização deve permanecer desacoplada. O projeto pode usar inicialmente Godot nativo em uma máquina com sessão gráfica mínima/OBS e, depois, experimentar render offscreen/headless + encoder.

## Loop do MVP-001

1. Simulator gera `LiveEvent`.
2. Tick/Aggregator agrupa eventos.
3. Parser determinístico cria `Intent`.
4. Action Mapper cria `ProposedAction`.
5. Runtime valida a proposta.
6. Ação aceita gera `Delta`; ação rejeitada não muda versão.
7. Runtime aplica o delta e incrementa `world_version`.
8. WorldStore persiste delta, evento e versão.
9. Renderer Godot recebe somente snapshot inicial e deltas posteriores.
10. Narration gera texto por template e Piper sintetiza uma única voz.
11. Admin Web exibe estado, métricas e preview.
12. Em idle, animações locais podem continuar, sem obrigar LLM ou criar deltas de mundo.

## Requisitos de desacoplamento

- LLM não pode alterar estado diretamente.
- Godot não pode escrever no World State diretamente.
- Admin Web não pode se tornar fonte de verdade.
- TTS não participa de decisões de estado.
- Memoria.ia não deve receber conceitos específicos do renderer no core.
- World Runtime depende da interface `WorldStore`, não da implementação da Memoria.ia.
- A evolução da Memoria.ia para suportar OFF.IA, servidor e Live Infinita deve ocorrer por primitives genéricas/Memory Spaces/adapters, sem criar um core específico para o jogo.

## Métricas mínimas

Cada tick deve registrar:

- `tick_id`
- eventos recebidos/filtrados
- intenções extraídas
- propostas aceitas/rejeitadas
- tempo de validação
- tempo de aplicação do delta
- tempo de persistência
- latência de entrega ao renderer
- `world_version`
- contagem de entidades/relações
- quando houver LLM: tokens, modelo, TTFT e custo
- quando houver áudio: tempo até primeiro áudio
- Continuity Error Rate (CER)

## Princípio de custo

O MVP-001 deve ser executável sem GPU dedicada e sem API paga obrigatória. A primeira baseline deve privilegiar CPU, vídeo integrado quando possível, Piper local, Simulator e persistência local. A nuvem entra apenas onde trouxer ganho mensurável.
