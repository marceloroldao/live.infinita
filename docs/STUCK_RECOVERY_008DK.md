# 008DK — retorno ao início quando Nov fica preso

O motor continua tentando os passos locais normais. Um monitor detecta confinamento dentro de 2,5 m por trinta segundos de tentativas, ou noventa segundos sem redução significativa da distância ao objetivo. Pausa, chegada e mudança de objetivo reiniciam o monitor. Caminhada com progresso não dispara recuperação.

Quando dispara, o renderer pausa o movimento e carrega os objetos da região inicial antes de consultar a física. Após um frame de física procura um ponto em até 32 m do início, livre para o corpo e com ao menos uma saída de dois metros válida. Se nenhum ponto for seguro, restaura a posição anterior e continua tentando. Se for seguro, interrompe a caminhada e reposiciona Nov com velocidade zero e câmera reiniciada naquele ponto.

Retorno é recuperação explícita, não aprendizado de saída nem caminhada bem-sucedida: não acrescenta chegada, passos, distância ou qualidade de rota. RAM e experiências persistentes são preservadas. O painel mostra retornos ao início separadamente.

A recuperação ocorre no renderer local e na prévia web; não escreve World State. O tour offline usado nos testes de apresentação não dispara o monitor. A contagem da sessão publicada é do renderer nativo.

Instalação: sudo bash /home/etbra/live.infinita/deploy/apply-stuck-recovery-008dk-root.sh

Requer recarregar a página após aplicar. Não corrige por si só a geometria que criou o buraco; evita permanência indefinida enquanto os próximos ajustes tratam o relevo.

Validação: 117 testes Python e 27 verificações Godot passaram. O teste inclui movimento real preso em paredes com desnível, rejeição do início ocupado, busca de outro ponto, registro sem chegada/distância fictícia e a integração assíncrona que carrega um obstáculo antes da escolha final e reposiciona a câmera. O teste de integração foi repetido após o ajuste do monitor para destinos rejeitados.
