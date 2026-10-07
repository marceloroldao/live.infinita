# 008EI — verificação na live após aplicação

Verificado em 2026-10-07T23:14:44Z. O segundo rollout terminou com `008EI_OK`, versão pública `36e4d95`, sinalizador de contorno local ativo. Os sete scripts nativos e a ponte Python coincidem com o código aplicado. Renderer reiniciado às 23:04:44 UTC, ativo e sem reinícios automáticos. Nenhum erro GDScript/parse/load encontrado no journal desse reinício até a coleta.

O estado registra 51 resultados locais, 51 registros locais e 37 registros recuperados já carregados pelo renderer. O último ciclo concluído da ponte confirma 37 eventos, 37 recuperados no cache, com 4 novas confirmações naquele ciclo. O renderer consulta o cache em intervalo próprio; contadores podem diferir durante sincronização. Os documentos privados da ponte não foram abertos: confirmação observada via journal e recuperação carregada observada via estado público do renderer.

Todos os resultados locais desta coleta têm identidade única, `contour_completed / executed_exit` e avanço físico de pelo menos 0,75 m. Há 2 chegadas, 0 resgates e 0 interrupções nesta sessão. Contornos incompletos excluídos: {"new_contact_before_executed_exit": 3}. Decisões de exploração: 12; mudanças iniciais causadas por preferência de padrões: 0; destas, atribuídas ao núcleo recuperado: 0.

O bloqueio anterior de ingestão foi resolvido e experiências reais da live estão sendo registradas e recuperadas. Ainda não foi demonstrada vantagem do aprendizado na live: registrar e recuperar não basta. A próxima medição deve ligar decisões alteradas às observações recuperadas e comparar custos/falhas em condições equivalentes, controlando mudanças de cenário. Não houve reinício, limpeza de memória ou experimento induzido pelo Codex durante esta verificação.

Evidências: `LOCAL_CONTOUR_PRODUCTION_008EI.json`, `LOCAL_CONTOUR_ROLLOUT_008EI.txt` e `LOCAL_CONTOUR_BRIDGE_PRODUCTION_008EI.txt`.
