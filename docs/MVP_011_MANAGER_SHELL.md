# MVP-011 — manager na página principal

O endereço principal `https://live.etbra.com.br/` abre uma tela de login e,
depois da autenticação, o manager de integrações. A senha é a chave de operador
já configurada na VM; ela é validada no servidor e não fica salva no
`sessionStorage` ou disponível ao JavaScript após o login.

## Endereços

- `/`: login e manager.
- `/manage/`: redirecionamento compatível para `/`.
- `/godot/`: exportação Web do Godot em `/var/www/live-infinita-godot`.
- `/gdscript/`: renderer PixiJS/GDScript anterior.

## Sessão

O login cria um cookie `HttpOnly`, `Secure` e `SameSite=Strict`, válido por 12
horas. O cookie contém somente o prazo e uma assinatura HMAC derivada da chave
do operador; a senha não é gravada no navegador. O acesso via Bearer continua
disponível para scripts operacionais existentes.

## Atualização da VM

O script `deploy/update-mvp011.sh` valida a versão instalada, cria backup do
código, do nginx e dos dados, instala a nova interface, valida o nginx, reinicia
o serviço e testa as três rotas. Em caso de falha, restaura o MVP-010.

Depois da primeira atualização, execute `deploy/enable-https-mvp011.sh` uma vez
para emitir o certificado, redirecionar HTTP para HTTPS e tornar a sessão de
login utilizável com transporte seguro.
