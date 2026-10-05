# 008DI — entrega do painel no navegador

A captura do celular mostrava o estado de espera, embora o renderer nativo tivesse contadores recentes. A consulta HTTP usava URL relativa. A publicação dos contadores dependia da conclusão da sincronização de episódios, promoções e recall.

O cliente agora constrói URLs HTTP absolutas com a origem da página. Um publicador sem acesso de rede publica status.json a cada cinco segundos, independentemente da API de memória. O cliente consulta esse status separadamente. O recall continua com sua origem e identidade próprias; status não é evidência de memória.

O publicador valida mundo, idade e contadores com o contrato existente. Fonte ausente, inválida ou antiga produz status vazio, sem zeros artificiais. Um recall atrasado não sobrescreve contadores mais novos.

Instalação: sudo bash /home/etbra/live.infinita/deploy/apply-panel-delivery-008di-root.sh

A instalação possui backup e rollback e publica a versão web. Após aplicar, recarregue a fonte do navegador. Testes verificam URLs absolutas, entrega ao consumidor, independência da API, expiração, mundo e ordem das atualizações. A verificação no navegador do celular ocorre após a instalação.

Validação: 110 testes Python, 26 verificações Godot e entrega HTTP real com servidor de fixture local passaram. O fixture usa HTTPRequest e o mesmo callback de produção até o consumidor.
