# AI Router

Camada de inferência substituível.

## V0.x

Provider inicial: OpenAI API.

## Futuro

- llama.cpp
- vLLM
- modelos locais especializados
- roteamento por custo/latência/disponibilidade

O contrato externo do serviço não deve depender do provider. A entrada deve conter contexto compilado e orçamento de latência; a saída deve ser estruturada e validável.
