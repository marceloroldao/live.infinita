# 008DL — transição gradual de novos vértices do relevo

A 008DK foi confirmada instalada. O renderer registrou retorno de (44,7; -458,4) ao início (-352; -32), e depois concluiu outro destino. A recuperação permanece ativa.

A inspeção encontrou um multiplicador abrupto de altura em x=175/z=-70 e a possibilidade de amostras novas de inferência criarem transições muito íngremes em relação às já consolidadas. O primeiro agora usa uma faixa suave de 64 m. Novos vértices de oito metros são limitados por um envelope dos vizinhos conhecidos em até três células, com inclinação de 0,65 m/m quando as restrições são compatíveis.

Nenhum vértice já consolidado se move. Triângulos, passos, câmera e objetos continuam compartilhando a mesma consulta de altura. Se amostras antigas forem incompatíveis, o algoritmo preserva as antigas, limita pela mais próxima e registra o conflito; isso não garante que qualquer mapa anterior possa ser corrigido sem reconstrução. Amostras remotas sem vizinhos permanecem definidas pela projeção cognitiva.

O teste impõe uma proposta de queda de 24 m, verifica a primeira transição limitada a 5,2 m por oito metros, caminha pelo terreno real e confere as bordas renderizadas. A recuperação da 008DK continua sendo o recurso para situações que ainda não tenham saída.

Instalação: sudo bash /home/etbra/live.infinita/deploy/apply-ground-blending-008dl-root.sh

Após aplicar, recarregue a página. A instalação reinicia o renderer para reconstruir os vértices da nova sessão. Não altera bancos de memória.

Validação: 28 verificações Godot passaram. O cenário de queda proposta de 24 m foi atravessado caminhando por 24 m, sem retorno automático; conferidas bordas idênticas dos terrenos e preservação dos vértices antigos. A sessão de produção da 008DK registrou sete chegadas e um retorno enquanto a 008DL ainda não estava instalada.
