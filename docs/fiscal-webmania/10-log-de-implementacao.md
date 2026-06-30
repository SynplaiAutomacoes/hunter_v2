# Log de implementacao fiscal

## Fase 3.5.0 - reavaliacao documental apos NFS-e legada

- Fase 3.4.1 reconhecida como validada no checkpoint `5865c74d59459ce1f347d8a36a217098f20cb5a9`.
- Confirmado no codigo que existem `NfseCancellation`, `NfseSubstitutionPreview`, `NfseSubstitution`, reconciliacao GET-only e capacidade municipal com `manifestation_enabled`; nao existe service de manifestacao NFS-e nem emissao manual nova fiscal.
- Comparados manifestacao NFS-e, emissao manual nova, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos `112120`, `112140`, `211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.
- Decisao recomendada: proxima fase propria para manifestacao de NFS-e Padrao Nacional, por ser o menor bloco com valor relevante e melhor reaproveitamento da infraestrutura ja validada.
- OpenAPI validado revisado como suficiente; nenhum schema ou endpoint foi alterado.
- Nenhum codigo funcional, migration, service, view, form, template, teste ou comando operacional foi alterado.
- Status posterior: Fase 3.5.0 aprovada pelo usuario e encerrada como validada.

## Fase 3.6.0 - planejamento tecnico da manifestacao NFS-e

- Fase 3.5.0 aprovada; autorizada somente documentacao para planejar manifestacao NFS-e Padrao Nacional.
- Revalidado contrato oficial Webmania NFS-e: `POST /2/nfse/manifestar`, `ambiente`, `chave|uuid`, `manifestador=1/2`, `evento=1/2`, rejeicao com `motivo_rejeicao` e justificativa condicional.
- Registrada lacuna: `/2/nfse/status` nao confirma claramente `manifestar` em `funcoes`; capability/Padrao Nacional devem bloquear sem confirmacao.
- Decisao documental: implementar futuramente de forma direta e pequena, sem preview previa, com model `NfseManifestation`, tentativa `nfse_manifestation`, payload congelado, timeout `uncertain`, webhook sem ambiguidade e reconciliacao sem POST.
- Nenhum codigo funcional, migration, service, view, form, template ou teste foi alterado.
- Status posterior: Fase 3.6.0 validada documentalmente e commitada no checkpoint `0a8dd0c9`.

## Fase 3.6.1 - implementacao da manifestacao NFS-e Padrao Nacional

- Autorizada implementacao restrita a manifestacao de NFS-e Padrao Nacional.
- Criados `NfseManifestation`, operation type `nfse_manifestation`, service `nfse_manifestation`, views/rotas/UI minima, webhook e reconciliacao consultiva.
- Payload transmitido restrito a `ambiente`, `uuid`, `manifestador`, `evento`, `motivo_rejeicao` e `justificativa_rejeicao` quando aplicavel.
- Municipal legado sem Padrao Nacional, NFS-e cancelada/substituida/incerta, NFS-e recebida/importada de terceiro e desfazimento de manifestacao permanecem bloqueados.
- Fase validada e encerrada no checkpoint `da3b2b48`: PostgreSQL normalizado para validacao, teste focado da manifestacao aprovado, regressoes diretas de NFS-e aprovadas, `manage.py check`, migration-check, Ruff focado e diff-check aprovados.

## Fase 3.7.0 - reavaliacao documental apos manifestacao NFS-e

- Fase 3.6.1 reconhecida como validada no checkpoint `da3b2b48`.
- Comparados emissao manual nova de NFS-e, NFS-e recebida/importada, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120`, `112140`, `211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.
- Decisao recomendada: **Opcao F**, criar fase preparatoria `3.7P - Preview de emissao manual nova de NFS-e`, sem transmissao, antes de qualquer `POST /2/nfse/emissao`.
- Justificativa: emissao manual nova tem maior valor de produto e reaproveita infraestrutura NFS-e, mas os dados locais ainda precisam ser congelados para evitar RPS/NFS-e com tomador, servico, valores, ISS/IBS-CBS ou capability mutaveis.
- OpenAPI validado revisado como suficiente; nenhum schema alterado.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.
- Status posterior: Fase 3.7.0 validada documentalmente e commitada no checkpoint `1b60125c`.

## Fase 3.7P - inicio da preview imutavel de emissao manual nova

- Fase 3.7.0 validada no checkpoint `1b60125c`.
- Autorizada somente preview/snapshot imutavel de emissao manual nova de NFS-e.
- Auditoria confirmou que a emissao legada reserva RPS e cria tentativa apenas na transmissao; a 3.7P deve validar RPS informado sem consumir contador oficial.
- Cancelamento, substituicao e manifestacao NFS-e ja possuem trilhas proprias e nao devem ser alterados para transmitir a preview manual.
- `POST /2/nfse/emissao`, `FiscalEmissionAttempt`, `NfseItem`, XML/DANFSE, webhook e reconciliacao remota permanecem bloqueados nesta fase.

## Fase 3.7P - validacao local

- Implementado `NfseManualEmissionPreview` com snapshots de RPS, tomador, servico, valores, tributacao, retencoes e IBS/CBS.
- Adicionadas flags conservadoras em empresa Webmania e capability municipal; ambas precisam estar habilitadas para criar/aprovar preview.
- Criacao e aprovacao permanecem locais: nenhum `POST /2/nfse/emissao`, `FiscalEmissionAttempt`, `NfseItem`, XML, DANFSE, webhook ou reconciliacao remota foi introduzido.
- Validacoes executadas:
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseManualEmissionPreviewTests --keepdb`
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseCancellationTests apps.finance.tests.FiscalPhaseThreeNfseManifestationTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionTests --keepdb`
  - `uv run python manage.py makemigrations finance --check --dry-run`
  - `uv run ruff check ...` nos arquivos Python tocados
  - `uv run mypy .` executado; falhou por baseline preexistente amplo, incluindo stubs ausentes e erros historicos fora do escopo.
- Status posterior: Fase 3.7P validada e encerrada no checkpoint `1fdded4e`.

## Fase 3.7.1 - inicio da emissao manual nova a partir de preview aprovada

- Fase 3.7P aprovada no checkpoint `1fdded4e`.
- Autorizada somente emissao manual nova de NFS-e consumindo `NfseManualEmissionPreview` aprovada.
- Contrato remoto revalidado localmente no OpenAPI validado: `POST /2/nfse/emissao`, Bearer v2, request body `NfseEmission`, resposta NFS-e com status e campos de download (`xml`, `pdf_nfse`, `pdf_rps`).
- A emissao deve enviar somente o `request_payload` congelado; nao pode recalcular tomador, servico, valores, tributacao, retencoes, IBS/CBS ou RPS.
- Cancelamento, substituicao e manifestacao da nova NFS-e, NFS-e recebida/importada, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria continuam bloqueados.

## Fase 3.7.1 - implementacao e validacao tecnica

- Criados `NfseManualEmission`, operation type `nfse_manual_emission`, flag administrativa separada, service remoto idempotente, views/rotas/UI minima, webhook e reconciliacao consultiva.
- A emissao envia exatamente o `request_payload` aprovado da preview para `POST /2/nfse/emissao`; nao ha conversao do contrato da preview nem recomposicao a partir de cadastros mutaveis.
- `NfseItem` passa a admitir `workorder` nula para representar NFS-e manual nova confirmada sem OS mutavel; nenhum `FiscalDocument(nfse)` foi introduzido.
- Auto-revisao reforcou validacao de RPS/serie da resposta, bloqueio de tipos invalidos em download e reconciliacao sem reenvio.
- Validacoes executadas:
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseManualEmissionTests --keepdb`
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseCancellationTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionTests apps.finance.tests.FiscalPhaseThreeNfseManifestationTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionTests --keepdb`
  - `uv run python manage.py makemigrations finance --check --dry-run`
  - `uv run ruff check ...` nos arquivos Python tocados
  - `uv run mypy .` executado; falhou por baseline amplo preexistente, com 3197 erros em 261 arquivos.
- Regressao adicional fora da bateria obrigatoria (`NfseEmissionServiceTests`, NFC-e manual simples, credito tipo 1 e debito tipo 4) nao foi usada como bloqueante: falhou em fixtures legadas de `NfseEmissionServiceTests` com `SimpleNamespace` e em uma constraint preexistente de documento de credito dentro de teste de debito.
- Permanecem fora do escopo: cancelamento, substituicao e manifestacao da nova NFS-e; NFS-e recebida/importada; CT-e, MDF-e, NFCom, DC-e; eventos IBS/CBS `112120/112140/211xxx`; creditos 2-5; debitos 1-3/5-8; complementar tributaria.
- Status posterior: Fase 3.7.1 validada e encerrada no checkpoint `2cb35206`.

## Fase 3.8.0 - reavaliacao do ciclo pos-emissao manual NFS-e

- Fase 3.7.1 aprovada no checkpoint `2cb35206`.
- Registrado que a emissao manual nova de NFS-e usa exclusivamente preview aprovada, `NfseManualEmission`, tentativa `nfse_manual_emission`, `NfseItem` somente apos confirmacao valida e webhook/reconciliacao consultivos sem repetir `POST`.
- Revalidada documentacao Webmania NFS-e para `/2/nfse/emissao`, `/2/nfse/cancelar`, `/2/nfse/substituir`, `/2/nfse/manifestar`, `/2/nfse/consulta/{identifier}` e `/2/nfse/status`.
- Matriz comparou cancelamento, substituicao, manifestacao, NFS-e recebida/importada, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.
- Decisao recomendada: **Opcao A**, implementar `Fase 3.8.1 - Cancelamento da NFS-e Manual Nova` como extensao segura do cancelamento NFS-e existente.
- OpenAPI validado permaneceu suficiente; nenhuma alteracao aplicada.
- Status posterior: Fase 3.8.0 validada documentalmente e commitada no checkpoint `1faf0a9`.

## Fase 3.8.1 - inicio do cancelamento da NFS-e manual nova

- Fase 3.8.0 aprovada no checkpoint `1faf0a9`.
- Autorizado somente cancelamento da NFS-e manual nova, via extensao segura do cancelamento NFS-e existente.
- Contrato remoto: `PUT /2/nfse/cancelar` com payload estrito `{uuid, motivo}`.
- Devem ser preservados `NfseManualEmissionPreview`, `NfseManualEmission.request_payload` e XML original da NFS-e; XML de cancelamento fica separado.
- Substituicao/manifestacao da nova NFS-e e demais blocos fiscais permanecem fora de escopo.

## Fase 3.8.1 - implementacao e validacao tecnica

- Implementada extensao segura de `NfseCancellation` para NFS-e manual nova.
- Migration `0068` torna `NfseCancellation.request` opcional; `item` continua obrigatorio e a constraint ativa por NFS-e permanece.
- `cancel_nfse_item` agora aceita `NfseItem` manual somente com `NfseManualEmission` vinculada, status autorizado, UUID seguro, capability de cancelamento ativa e sem cancelamento ativo/incerto.
- Payload remoto comprovado por testes: somente `{uuid, motivo}` em `PUT /2/nfse/cancelar`.
- Webhook de `status=cancelado` confirma cancelamento manual antes de tratar payload como atualizacao da emissao manual; reconciliacao consulta sem reenviar `PUT`.
- UI minima adicionada ao detalhe da emissao manual; payload/XML de cancelamento protegidos por `cancel_nfse`.
- Validacoes executadas:
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseCancellationTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionTests --keepdb`
  - `uv run python manage.py makemigrations finance --check --dry-run`
  - `uv run ruff check ...` nos arquivos Python tocados
- Permanecem fora do escopo: substituicao/manifestacao da NFS-e manual, NFS-e recebida/importada, emissao manual adicional, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.
- Status posterior: Fase 3.8.1 validada e encerrada no checkpoint `29f3f3a9`.

## Fase 3.9.0 - reavaliacao apos ciclo minimo da NFS-e manual

- Fase 3.8.1 reconhecida como validada no checkpoint `29f3f3a9`.
- Registrado ciclo minimo completo da NFS-e manual: preview imutavel, emissao a partir de preview aprovada e cancelamento por `NfseCancellation`.
- Confirmado que `NfseCancellation.request` agora e opcional para origem manual, o contrato remoto do cancelamento segue `PUT /2/nfse/cancelar` com `{uuid, motivo}`, o XML original e preservado e o XML de cancelamento fica separado.
- Comparados substituicao da NFS-e manual, manifestacao da NFS-e manual, NFS-e recebida/importada, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120`, `112140`, `211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.
- Decisao recomendada: **Opcao A**, implementar substituicao da NFS-e manual como extensao segura do fluxo atual de substituicao NFS-e, reutilizando `NfseSubstitutionPreview`, `NfseSubstitution`, `POST /2/nfse/substituir`, idempotencia, webhook e reconciliacao ja validados.
- OpenAPI validado revisado como suficiente; nenhuma alteracao aplicada.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.

- Status posterior: Fase 3.9.0 validada documentalmente e commitada no checkpoint `21d684e7`.

## Fase 3.9.1 - implementacao da substituicao da NFS-e manual

- Fase 3.9.0 aprovada no checkpoint `21d684e7`.
- Implementada extensao segura de `NfseSubstitutionPreview`/`NfseSubstitution` para aceitar `NfseItem` originado por `NfseManualEmission`.
- Removida exigencia de `NfseRequest` para original manual; quando nao ha request, exige `NfseManualEmission` vinculada e capability de substituicao ativa na preview manual.
- Payload remoto preservado: `POST /2/nfse/substituir` recebe somente `ambiente`, `codigo_verificacao`, `motivo` e `rps` aprovados na preview.
- Substituta manual e criada como nova `NfseItem` somente apos confirmacao remota valida; original manual so e marcada `substituido` apos confirmacao.
- XML original da NFS-e manual, preview manual e payload da emissao manual permanecem imutaveis; XML/PDF da substituta ficam separados.
- UI minima adicionada ao detalhe da emissao manual para preparar substituicao elegivel.
- Validacoes executadas:
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseManualEmissionTests --keepdb`
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseSubstitutionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionConcurrentTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionTests apps.finance.tests.FiscalPhaseThreeNfseCancellationTests --keepdb`
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseManifestationTests --keepdb`
  - `uv run python manage.py makemigrations finance --check --dry-run`
  - `uv run ruff check apps/finance/forms/nfse_substitution_preview.py apps/finance/services/nfse_substitution.py apps/finance/services/nfse_substitution_preview.py apps/finance/views/nfse_manual_emission.py apps/finance/views/nfse_substitution_preview.py apps/finance/tests.py`
  - `git diff --check`
  - `uv run mypy .` executado como nao bloqueante; falhou no baseline preexistente com 3205 erros em 261 arquivos.
- Permanecem fora do escopo: manifestacao da NFS-e manual, NFS-e recebida/importada, emissao manual adicional, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.

## Fase 3.10.0 - reavaliacao da manifestacao da NFS-e manual

- Fase 3.9.1 aprovada, validada e encerrada no checkpoint `99254f33`.
- Registrado que a substituicao da NFS-e manual reutiliza `NfseSubstitutionPreview`, `NfseSubstitution`, `operation_type="nfse_substitution"` e `POST /2/nfse/substituir`, preservando XML original e criando nova `NfseItem` substituta somente apos confirmacao remota valida.
- Revalidada documentacao oficial Webmania NFS-e para `POST /2/nfse/manifestar`: manifestacao de participacao no Padrao Nacional, por tomador ou intermediario, com payload de `ambiente`, `uuid|chave`, `manifestador`, `evento` e campos de rejeicao quando aplicavel.
- Matriz documental comparou NFS-e manual autorizada, substituta, cancelada, substituida, uncertain, sem UUID, sem Padrao Nacional, NFS-e recebida/importada e NFS-e legada municipal.
- Decisao recomendada: **Opcao B**, adiar manifestacao da NFS-e manual por ambiguidade de papel fiscal da oficina como tomadora/intermediaria em nota emitida pela propria oficina.
- Opcao C permanece como provavel proximo planejamento: preparar NFS-e recebida/importada antes de ampliar manifestacao para documentos de terceiros.
- OpenAPI validado revisado como suficiente; nenhuma alteracao aplicada.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.

## Fase 3.11.0 - planejamento tecnico da NFS-e recebida/importada

- Fase 3.10.0 validada documentalmente e commitada no checkpoint `8d5c7192`.
- Registrada decisao aprovada: manifestacao da NFS-e manual adiada; priorizar preparacao de NFS-e recebida/importada de terceiros.
- Revalidada documentacao oficial Webmania NFS-e para consulta por identificador, `/status`, manifestacao Padrao Nacional e webhooks. Nao foi encontrado endpoint REST claro de importacao/sincronizacao de NFS-e recebida que forneca XML completo, identidade e papel fiscal.
- Matriz de origem comparou upload XML, consulta por identificador, webhook sem documento previo, digitacao manual, importacao por lote e integracao futura e-mail/ERP.
- Matriz de papel fiscal comparou tomador, intermediario, prestador, desconhecido, multiplos papeis e CNPJ divergente.
- Decisao recomendada: **Opcao A**, criar preview/registro local de NFS-e recebida a partir de XML validado, sem manifestacao funcional.
- OpenAPI validado revisado como suficiente para consulta/status/manifestacao; nenhuma alteracao aplicada.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.
- Status posterior: Fase 3.11.0 validada documentalmente e commitada no checkpoint `6f36f7fc`.

## Fase 3.11.1 - inicio do registro local de NFS-e recebida por XML

- Fase 3.11.0 aprovada no checkpoint `6f36f7fc`.
- Autorizado somente registro local unitario de NFS-e recebida/importada de terceiros a partir de upload manual de XML.
- Fonte inicial: XML validado localmente; consulta Webmania por identificador, webhook sem documento previo, digitacao manual, lote e e-mail/ERP permanecem fora do escopo.
- Nao criar manifestacao funcional, `NfseItem`, `FiscalDocument(nfse)`, `FiscalEmissionAttempt` ou chamada Webmania nesta fase.
- Devem ser implementados hash/snapshot XML, validacao de papel fiscal da oficina, duplicidade, cross-workshop, permissoes proprias e UI minima protegida.

## Fase 3.11.1 - implementacao e validacao tecnica

- Criados `WebmaniaCompany.nfse_received_import_enabled` e `NfseReceivedDocument` pela migration `0069_webmaniacompany_nfse_received_import_enabled_and_more.py`.
- Implementado servico local de importacao por XML com hash SHA-256 do XML normalizado, snapshot imutavel, extracao de UUID/identificador/codigo, CNPJs, municipio, ambiente, data, valor e status remoto do XML.
- Validacao bloqueia XML invalido/inseguro, duplicidade por hash/UUID/identificador, papel fiscal desconhecido/multiplo, status cancelado/substituido/anulado, empresa de outra oficina e colisao com NFS-e ja emitida localmente.
- UI minima adicionada para lista, importacao, detalhe, payload sanitizado e download do XML original, com permissoes `import_nfse_received`, `view_nfse_received`, `view_nfse_received_payload` e `download_nfse_received_xml`.
- Auto-revisao confirmou ausencia de chamada Webmania, `NfseManifestation`, `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt` neste fluxo.
- Validacao: 6 testes especificos da fase e 57 testes regressivos NFS-e passaram; `makemigrations finance --check --dry-run`, Ruff nos Python tocados e `git diff --check` passaram.
- `mypy .` executado e nao bloqueante: falha por baseline amplo preexistente (`3220 errors in 264 files`), incluindo stubs ausentes e erros tipados antigos fora da fase.

## Fase 3.12.0 - reavaliacao documental da manifestacao de NFS-e recebida

- Fase 3.11.1 aprovada e encerrada no checkpoint `b25ad698`; Fase 3.11.0 mantida como checkpoint documental `6f36f7fc`.
- Registrado que `NfseReceivedDocument`, importacao local por XML, `nfse_received_import_enabled`, snapshot/hash de XML e validacao de papel fiscal estao implementados.
- Confirmada documentalmente a ausencia de chamada Webmania, `NfseItem`, `FiscalDocument(nfse)`, `FiscalEmissionAttempt` e `NfseManifestation` no fluxo de importacao recebida.
- Revalidada documentacao oficial Webmania NFS-e para `POST /2/nfse/manifestar`: endpoint do Padrao Nacional, manifestador tomador/intermediario, eventos confirmacao/rejeicao, motivos `1..5/9`, justificativa obrigatoria somente no motivo `9` e sem endpoint claro de desfazimento.
- Matriz de elegibilidade comparou tomador, intermediario, prestador, desconhecido, multiplos papeis, CNPJ divergente, XML invalido/ausente, sem UUID, sem Padrao Nacional, cancelado, substituido, uncertain, duplicado e cross-workshop.
- Decisao recomendada: **Opcao A**, implementar futuramente manifestacao de NFS-e recebida como extensao segura de `NfseManifestation`, vinculada a `NfseReceivedDocument` validado, sem criar fluxo paralelo.
- Proxima fase sugerida: `3.12.1 - Manifestacao de NFS-e Recebida`, restrita a roles `taker` e `intermediary`, capability `national_standard_enabled` + `manifestation_enabled`, UUID seguro e webhook/reconciliacao sem repetir POST.
- OpenAPI validado considerado suficiente; nenhuma alteracao aplicada.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.
- Status posterior: Fase 3.12.0 validada documentalmente e commitada no checkpoint `a5b4f4b`.

## Fase 3.12.1 - inicio da manifestacao de NFS-e recebida

- Fase 3.12.0 aprovada no checkpoint `a5b4f4b`.
- Autorizada implementacao somente da manifestacao de `NfseReceivedDocument` validado, como extensao segura de `NfseManifestation`.
- Escopo: `POST /2/nfse/manifestar`, roles `taker` e `intermediary`, UUID seguro, XML validado, Padrao Nacional e capability `manifestation_enabled`.
- Permanecem fora de escopo: manifestacao da NFS-e manual, emissao, cancelamento ou substituicao de NFS-e recebida, consulta Webmania como fonte de importacao, lote, e-mail/ERP, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes e complementar tributaria.
- Regras de seguranca: nao criar `NfseItem`, nao criar `FiscalDocument(nfse)`, nao alterar XML recebido e nao alterar dados fiscais extraidos.

## Fase 3.12.1 - implementacao e validacao tecnica

- `NfseManifestation` foi estendida com origem alternativa `received_document`, mantendo `nfse_item` para origem local e exigindo exatamente uma origem fiscal.
- Implementado service de manifestacao de NFS-e recebida com payload restrito a `ambiente`, `uuid`, `manifestador`, `evento`, `motivo_rejeicao` e `justificativa_rejeicao`, sem XML, CNPJ, dados extraidos ou payloads de emissao/cancelamento/substituicao.
- Elegibilidade exige `NfseReceivedDocument` validado, XML snapshot/hash, UUID remoto, role `taker` ou `intermediary`, capability municipal unica, `national_standard_enabled=True`, `manifestation_enabled=True`, status nao cancelado/substituido/incerto e ausencia de manifestacao ativa/sucedida/incerta duplicada.
- UI minima adicionada no detalhe da NFS-e recebida, com formulario de confirmacao/rejeicao, historico, payload e XML da manifestacao protegidos por permissoes de `NfseManifestation`.
- Webhook/reconciliacao existentes foram preservados para `modelo=manifestacao_nfse`; timeout permanece `uncertain` e bloqueia reenvio sem repetir POST.
- Auto-revisao corrigiu lock PostgreSQL em `select_for_update` com FKs opcionais, limitando o bloqueio a linha da manifestacao.
- Validacoes executadas:
  - `uv run python manage.py makemigrations finance --check --dry-run`
  - `uv run python manage.py test apps.finance.tests.FiscalPhaseThreeNfseReceivedDocumentTests apps.finance.tests.FiscalPhaseThreeNfseManifestationTests apps.finance.tests.FiscalPhaseThreeNfseReceivedManifestationTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseManualEmissionTests apps.finance.tests.FiscalPhaseThreeNfseCancellationTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionPreviewTests apps.finance.tests.FiscalPhaseThreeNfseSubstitutionTests --keepdb`
  - `uv run ruff check` nos Python tocados
- Permanecem fora do escopo: manifestacao da NFS-e manual, emissao/cancelamento/substituicao de NFS-e recebida, `NfseItem`, `FiscalDocument(nfse)`, importacao por consulta Webmania/lote/e-mail/ERP e demais familias fiscais.
- Status posterior: Fase 3.12.1 validada e encerrada no checkpoint `6cc3a788`.

## Fase 3.13.0 - reavaliacao documental apos fechamento do bloco NFS-e

- Fase 3.12.1 aprovada, validada e encerrada no checkpoint `6cc3a788`.
- Registrado fechamento dos principais fluxos NFS-e: cancelamento legado, substituicao, manifestacao Padrao Nacional, preview manual, emissao manual, cancelamento manual, substituicao manual, registro local de NFS-e recebida por XML e manifestacao de NFS-e recebida.
- Confirmado que `NfseManifestation` agora aceita origem por `NfseReceivedDocument`, com migration `0070`, payload restrito de `POST /2/nfse/manifestar`, bloqueios por papel fiscal, UUID, XML/hash, status, Padrao Nacional, capability e duplicidade, sem `NfseItem` e sem `FiscalDocument(nfse)` para recebidas.
- A manifestacao da NFS-e manual permanece adiada porque o papel fiscal da oficina como tomadora/intermediaria em documento emitido por ela propria continua sem confirmacao segura.
- Reavaliados consulta Webmania para NFS-e recebida, importacao em lote, integracao e-mail/ERP, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.
- Decisao recomendada: **Opcao A**, planejar consulta/reconciliacao auxiliar para `NfseReceivedDocument`, estritamente consultiva, sem criar documento recebido sem XML, sem substituir XML validado, sem manifestar automaticamente, sem `NfseItem` e sem `FiscalDocument(nfse)`.
- OpenAPI validado permanece suficiente; nenhuma correcao oficial nova foi aplicada.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado nesta fase documental.
- Status posterior: Fase 3.14.0 validada documentalmente e commitada no checkpoint `18d1840d`.

## Fase 3.14.1 - implementacao e validacao tecnica

- Criados `NfseReceivedImportBatch` e `NfseReceivedImportBatchItem` pela migration `0072`.
- Implementado service de lote XML-only que reaproveita parser/importador unitario, isola erros por arquivo e permite importacao parcial auditavel.
- Implementados limites de 20 arquivos, 2 MB por XML e 20 MB por lote, com bloqueio de extensao insegura, arquivo vazio e conteudo nao XML.
- Implementada UI minima com upload multiplo, relatorio por arquivo, totais e links para documentos importados.
- Permissoes especificas: `import_nfse_received_batch` e `view_nfse_received_batch`; flag reaproveitada: `nfse_received_import_enabled`.
- Validacoes: `makemigrations finance --check --dry-run` OK; 6 testes focados OK; 79 testes fiscais direcionados OK; Ruff nos Python tocados OK.
- Nao foram iniciados consulta Webmania automatica, manifestacao automatica/manual, documento sem XML, e-mail/ERP, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, IBS/CBS pendentes, creditos/debitos pendentes ou complementar tributaria.
- Status posterior: Fase 3.14.1 validada e encerrada no checkpoint `b53e862b`.

## Fase 3.15.0 - reavaliacao apos consolidacao NFS-e recebida

- Fase 3.14.1 aprovada, validada e encerrada no checkpoint `b53e862b`.
- Registrado ciclo recebido completo: upload unitario XML, manifestacao recebida, consulta GET-only e lote XML auditavel.
- Reavaliados e-mail/ERP, consulta Webmania ampliada, manifestacao manual, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.
- Decisao recomendada: **Opcao A**, planejar integracao e-mail/ERP para XML NFS-e em fase exclusivamente preparatoria/documental.
- OpenAPI validado permanece suficiente; nenhuma correcao oficial nova foi aplicada.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado nesta fase documental.
- Status posterior: Fase 3.13.0 validada documentalmente e commitada no checkpoint `d83b37dc`.

## Fase 3.13.1 - inicio da consulta auxiliar de NFS-e recebida

- Fase 3.13.0 aprovada no checkpoint `d83b37dc`.
- Autorizada implementacao somente de consulta/reconciliacao auxiliar para `NfseReceivedDocument` ja validado por XML.
- Escopo: GET-only por `GET /2/nfse/consulta/{identifier}` e, se aplicavel, apoio de `/2/nfse/status`, com resultado consultivo e nao destrutivo.
- Devem permanecer imutaveis: `xml_snapshot`, `xml_hash`, UUID, CNPJs, municipio, ambiente, valor, papel fiscal e demais dados extraidos do XML.
- Permanecem fora de escopo: criacao de documento recebido sem XML, manifestacao automatica, `NfseItem`, `FiscalDocument(nfse)`, emissao/cancelamento/substituicao de recebida, lote, e-mail/ERP e fases fiscais posteriores.

## Fase 3.13.1 - implementacao e validacao tecnica

- Criados `WebmaniaCompany.nfse_received_consultation_enabled` e `NfseReceivedDocumentConsultation` pela migration `0071`.
- Implementado service consultivo para `NfseReceivedDocument` validado por XML, usando somente `GET /2/nfse/consulta/{identifier}` e registrando snapshot remoto separado.
- Divergencias de UUID, status remoto, CNPJs, municipio, ambiente, valor e Padrao Nacional sao registradas sem alterar XML/hash/dados extraidos do documento recebido.
- UI minima no detalhe de NFS-e recebida, historico de consultas, payload protegido e permissoes especificas de consulta/payload.
- Validacoes: `makemigrations finance --check --dry-run` OK; 4 testes focados OK; 73 testes fiscais direcionados OK; Ruff nos Python tocados OK; `git diff --check` OK.
- Nao foram iniciados manifestacao manual, emissao, cancelamento/substituicao de recebida, importacao por consulta, lote, e-mail/ERP, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos pendentes ou complementar tributaria.
- Status posterior: Fase 3.13.1 validada e encerrada no checkpoint `01f0924d`.

## Fase 3.14.0 - reavaliacao apos NFS-e recebida completa

- Fase 3.13.1 aprovada, validada e encerrada no checkpoint `01f0924d`.
- Registrado bloco NFS-e recebida completo com registro local por XML, manifestacao recebida e consulta/reconciliacao GET-only.
- Confirmado que `NfseReceivedDocumentConsultation`, migration `0071` e flag `nfse_received_consultation_enabled` foram implementados; XML/hash/dados extraidos permanecem preservados e divergencias sao consultivas.
- Reavaliados importacao em lote XML, e-mail/ERP, consulta Webmania ampliada, manifestacao manual, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS `112120/112140/211xxx`, creditos 2-5, debitos 1-3/5-8 e complementar tributaria.
- Decisao recomendada: **Opcao A**, implementar importacao em lote de XML de NFS-e recebida, sem consulta Webmania automatica, sem criacao sem XML, sem sobrescrever XML validado, sem manifestacao automatica, sem `NfseItem` e sem `FiscalDocument(nfse)`.
- OpenAPI validado permanece suficiente; nenhuma correcao oficial nova foi aplicada.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado nesta fase documental.

## Fase 3.4.1 - inicio

- Fase 3.4P validada no checkpoint `747b6750a62d6ed59bed84c4616f89793c4247b4`.
- `NfseSubstitutionPreview` aprovada e imutavel passa a ser a unica origem permitida do payload remoto.
- Contrato oficial revalidado em 2026-06-24: texto introdutorio ainda cita `uuid`, mas tabela/exemplo confirmam `ambiente`, `codigo_verificacao`, `motivo` e `rps`; nao sera enviado payload hibrido.
- Escopo autorizado: somente `POST /2/nfse/substituir`, idempotencia, confirmacao original/substituta, webhook/reconciliacao consultiva, permissoes e UI minima.
- Implementados `NfseSubstitution`, tentativa `nfse_substitution`, estado `NfseItem.substituido`, service remoto, webhook, reconciliacao GET-only, UI, payload e downloads protegidos pela migration `0064`.
- Auto-revisao adicionou rank terminal `substituido`, fallback seguro por `nfse_substituida.uuid`, bloqueio de ambiguidade e reconciliacao de respostas assíncronas sem novo POST.
- Validacao final: 66 testes direcionados passaram; `makemigrations --check`, ruff e `git diff --check` passaram.
- `mypy` nao bloqueante: 1118 erros no grafo de 118 arquivos; isolamento encontrou `requests` sem stubs e erro interno do `django-stubs`, sem mudar o baseline aceito.

## Fase 3.4P - inicio

- Fase 3.4.0 aprovada: criar preview imutavel do novo RPS antes da substituicao remota.
- Escopo autorizado: modelagem, validacao, permissao, feature flag e UI administrativa da preview, sem `POST /2/nfse/substituir`.
- Divergencia Webmania preservada: texto introdutorio menciona `uuid`, enquanto tabela/exemplo usam `ambiente`, `codigo_verificacao`, `motivo` e `rps`.
- Auditoria local confirmou que OS, tomador, classe fiscal e valores atuais sao mutaveis; a preview nao reutilizara `build_nfse_payload()` como snapshot implicito.
- Implementados `NfseSubstitutionPreview`, flag `nfse_substitution_preview_enabled`, quatro permissoes, service local, forms, views, URLs e templates pela migration `0063`.
- Validacao: 54 testes direcionados das Fases 1/3.1/3.2/3.3/3.4P passaram; `makemigrations --check`, ruff e `git diff --check` passaram.
- `mypy` foi executado como nao bloqueante e manteve 1110 erros preexistentes em 117 arquivos, incluindo dependencias sem stubs e modulos fora do escopo.
- Auto-revisao corrigiu lock PostgreSQL sobre FK anulavel, tornou o estado aprovado irreversivel por edicao e adicionou cobertura explicita do payload por permissao/tenancy.

Este arquivo deve ser atualizado a partir da primeira fase de codigo aprovada.

## Entradas

| Data       | Fase | Objetivo                      | Arquivos alterados       | Migrations | Testes executados | Decisoes       | Pendencias     | Riscos                                          | Proxima acao       |
| ---------- | ---- | ----------------------------- | ------------------------ | ---------- | ----------------- | -------------- | -------------- | ----------------------------------------------- | ------------------ |
| 2026-05-28 | 0    | Criar PRDs e OpenAPI validado | `docs/fiscal-webmania/*` | Nenhuma    | Nao aplicavel     | ADRs propostas | Aprovada pelo usuario | Docs podem ficar desatualizados se codigo mudar | Manter docs sincronizados |
| 2026-05-28 | 0.1  | Reforcar OpenAPI, divergencias e regras beta | `docs/fiscal-webmania/*` | Nenhuma | Parse JSON e contagem OpenAPI | Consultas NFS-e/MDF-e conforme exemplo oficial; classificacao NFCom/DC-e da epoca, superada na 2.6.0 | Aprovada pelo usuario | Schemas devem ser reconferidos antes de cada fase de codigo | Revalidar antes de novas familias |
| 2026-05-28 | 1    | Estabilizar NF-e/NFS-e existentes | `apps/finance/models/finance.py`, `apps/finance/models/__init__.py`, `apps/finance/migrations/0041_fiscalemissionattempt_and_more.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/services/nfe_emission.py`, `apps/finance/services/emission.py`, `apps/finance/services/tax_classes.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfe.py`, `apps/workshops/mixin.py`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0041_fiscalemissionattempt_and_more` | `FiscalPhaseOneStabilizationTests` e `FiscalPhaseOneConcurrentEmissionTests` OK; `makemigrations finance --check --dry-run` OK; ruff nos arquivos tocados OK; `git diff --check` OK; falhas globais aceitas como preexistentes | Manter `NfeRequest`/`NfseRequest`; tentativa persistida por intencao; `uncertain` bloqueia reenvio; webhook por fingerprint; NF-e usa permissao propria com fallback legado | Validada tecnicamente com dividas preexistentes registradas e aceitas pelo usuario | Reconciliacao e webhook nao emitem; tentativa incerta exige consulta/reconciliacao manual antes de nova emissao | Aguardar autorizacao explicita da Fase 2 |
| 2026-05-28 | 2.0  | Planejar expansao NF-e/NFC-e | `docs/fiscal-webmania/*` | Nenhuma | Revisao documental e rechecagem oficial NF-e/NFC-e | Recomendar nucleo minimo; usuario decidiu que `FiscalDocumentLink` fica somente para 2.2; dividir Fase 2 em 2.1 CC-e, 2.2 derivados, 2.3 NFC-e, 2.4 manifestacao/IBS-CBS | Aprovada pelo usuario | Endpoints e Reforma Tributaria devem ser revalidados antes de codigo | Fase 2.1 implementada para revisao |
| 2026-05-28 | 2.1  | Implementar CC-e Webmania | `apps/finance/models/finance.py`, `apps/finance/models/__init__.py`, `apps/finance/migrations/0042_fiscalemissionattempt_operation_type_and_more.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/services/nfe_events.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0042_fiscalemissionattempt_operation_type_and_more` | `makemigrations finance --check --dry-run` OK; `FiscalPhaseOne*` + `FiscalPhaseTwoCorrection*` OK com 27 testes; ruff nos arquivos Python tocados OK; `git diff --check` OK | Criar apenas `FiscalDocument`/`FiscalDocumentEvent`; `FiscalDocumentLink` fica para 2.2; CC-e e evento, nao nota comum; idempotencia por sequencia 1-20; webhook CC-e por UUID e fallback por chave+sequencia com ambiguidade rejeitada | Validada | Webmania CC-e deve ser reconferida em homologacao antes de producao; `uncertain` exige resolucao manual/reconciliacao futura | Aguardar autorizacao explicita da Fase 2.2 |
| 2026-05-28 | 2.2.0 | Revisar modelagem documental de derivados NF-e | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check` documental | Devolucao/estorno e complementar exigem `FiscalDocumentLink`; ajuste usa link opcional; NF-e externa ganha projecao minima; credito/debito vao para Fase 2.5 | Documentada; sem codigo autorizado | Revalidar payloads oficiais imediatamente antes de implementar cada subfase | Recomendar iniciar por Fase 2.2A |
| 2026-05-28 | 2.2A-doc | Corrigir decisoes antes do codigo de devolucao/estorno | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check` documental | NF-e externa valida formato e exige confirmacao, sem consulta padrao como garantia; idempotencia por documento derivado persistido | Documentada; Fase 2.2A autorizada apos esta correcao | Payloads oficiais ainda devem ser revalidados no gateway | Implementar somente Fase 2.2A |
| 2026-05-28 | 2.2A | Implementar e validar devolucao e estorno NF-e | `apps/finance/models/finance.py`, `apps/finance/migrations/0043_fiscaldocumentlink_alter_fiscaldocument_options_and_more.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/services/nfe_returns.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0043_fiscaldocumentlink_alter_fiscaldocument_options_and_more` | `makemigrations finance --check --dry-run` OK; `FiscalPhaseOne*`, `FiscalPhaseTwoCorrection*`, `FiscalPhaseTwoReturn*` OK com 45 testes; ruff nos arquivos Python tocados OK; `git diff --check` OK | Criar `FiscalDocumentLink`; persistir documento derivado antes do POST `/1/nfe/devolucao/`; idempotencia por documento derivado; parcial usa sequenciais fiscais e vetor `quantidade` alinhado; NF-e externa minima bloqueia parcial sem XML/importacao; webhook/reconciliacao atualizam somente derivado | Validada | UI local minima usa produtos JSON com sequencial fiscal; validacao externa por XML/API especifica permanece backlog | Aguardar autorizacao explicita da Fase 2.2B |
| 2026-05-28 | 2.2B.0 | Planejar Nota Fiscal Complementar | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check` documental | Complementar sera `FiscalDocument(purpose="complementary")` com subtipo `price_quantity`, `tax` ou `import_addition`; `FiscalDocumentLink(role="complements")` obrigatorio; idempotencia por documento derivado; externa minima bloqueia preco/quantidade sem XML/importacao | Documentada; codigo funcional nao autorizado | Revalidar payload oficial por subtipo antes do codigo; decidir politica final para complementar tributaria externa | Recomendar iniciar por `complementary_price_quantity` local |
| 2026-05-28 | 2.2B.1 | Implementar e validar Nota Fiscal Complementar de preco/quantidade local | `apps/finance/models/finance.py`, `apps/finance/migrations/0044_alter_fiscaldocument_options_and_more.py`, `apps/finance/services/nfe_complementary.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0044_alter_fiscaldocument_options_and_more` | `makemigrations finance --check --dry-run` OK; Fases 1, 2.1, 2.2A e 2.2B.1 direcionadas OK com 58 testes; ruff nos arquivos Python tocados OK; `git diff --check` OK | Complementar de preco/quantidade usa documento derivado local, link `complements`, tentativa `complementary_price_quantity`, payload congelado, webhook/reconciliacao somente no derivado; payload remove valores/quantidades originais e objetos tributarios/IBS-CBS fora do escopo | Validada; Fase 2.2B.2 nao iniciada | UI minima usa itens JSON; complemento externo preco/quantidade permanece bloqueado sem importacao/XML validada | Aguardar autorizacao explicita da Fase 2.2B.2 ou outra subfase |
| 2026-05-28 | 2.2C | Implementar e validar Nota Fiscal de Ajuste | `apps/finance/models/finance.py`, `apps/finance/migrations/0045_alter_fiscaldocument_options_and_more.py`, `apps/finance/services/nfe_adjustment.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0045_alter_fiscaldocument_options_and_more` | `makemigrations finance --check --dry-run` OK; Fases 1, 2.1, 2.2A, 2.2B.1 e 2.2C direcionadas OK com 68 testes; ruff nos arquivos Python tocados OK; `git diff --check` OK | Ajuste usa `/1/nfe/ajuste/`, `FiscalDocument(purpose="adjustment", origin="manual")`, link `adjusts` opcional, tentativa `adjustment`, idempotencia por documento de ajuste, validacao de `WebmaniaCompany.regime_tributario` e bloqueio de Simples/MEI/desconhecido; estorno SC/ES deve usar devolucao/estorno | Validada; Fase 2.2B.2 nao iniciada | Entrada avulsa ampla pela central fiscal permanece futura; UI atual e contextual no detalhe da NF-e | Aguardar autorizacao explicita da proxima subfase |
| 2026-05-29 | 2.3.0 | Planejar NFC-e documentalmente | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check` documental | NFC-e deve nascer em `FiscalDocument(document_type="nfce")`; configuracao usa `WebmaniaCompany` existente; emissao futura usa `/1/nfe/emissao/` com `modelo=2`; cancelamento/substituicao e contingencia/offline exigem decisao posterior | Documentada; codigo funcional nao autorizado | Revalidar campos oficiais de NFC-e, CSC e cancelamento por substituicao antes do codigo | Aguardar aprovacao explicita da Fase 2.3 funcional |
| 2026-05-29 | 2.3.1 | Iniciar implementacao de NFC-e manual simples | `docs/fiscal-webmania/*` e codigo Fase 2.3.1 | A definir | A executar | Fase 2.3.0 aprovada; NFC-e sera `FiscalDocument(document_type="nfce", purpose="normal", origin="manual")`; nao criar `NfceRequest`; usar `WebmaniaCompany` para configuracao; `modelo=2`, `finalidade=1`, `operacao=1` | Em implementacao | Contingencia/offline, cancelamento por substituicao, PDV/TEF/SAT/MFE, manifestacao, IBS/CBS, credito/debito e complementar tributaria fora do escopo | Implementar e validar somente Fase 2.3.1 |
| 2026-05-29 | 2.3.1 | Validacao interrompida por bloqueio de ambiente | `apps/finance/*`, `apps/workshops/forms/workshops.py`, `apps/workshops/templates/workshops/workshop_update.html`, `docs/fiscal-webmania/*` | `finance.0046_alter_fiscaldocument_options_and_more` proposta | `git diff --check` OK; `uv run python manage.py test apps.finance.tests.FiscalPhaseTwoNfceManualTests apps.finance.tests.FiscalPhaseTwoNfceManualConcurrentTests --keepdb` nao executou porque o sandbox nao acessou `C:\Users\vinic\AppData\Local\uv\cache` e a escalada foi recusada por limite de uso | Implementacao parcial inclui `nfce_enabled`, servico NFC-e manual, webhook/reconciliacao, UI minima, permissao e testes; validacao obrigatoria ainda pendente | Em implementacao; nao validada | Rodar comandos obrigatorios quando o ambiente permitir antes de checkpoint | Reexecutar validacoes e revisar antes de marcar validada |
| 2026-05-29 | 2.3.1 | Revisar, corrigir e validar NFC-e manual simples | `apps/finance/forms/webmania.py`, `apps/finance/models/finance.py`, `apps/finance/migrations/0046_alter_fiscaldocument_options_and_more.py`, `apps/finance/services/nfce_emission.py`, `apps/finance/tests.py`, `apps/finance/views/webmania.py`, `apps/workshops/forms/workshops.py`, `docs/fiscal-webmania/*` | `finance.0046_alter_fiscaldocument_options_and_more` | `makemigrations finance --check --dry-run` OK; 76 testes direcionados Fases 1, 2.1, 2.2A, 2.2B.1, 2.2C e 2.3.1 OK; testes especificos de protecao CSC OK; ruff nos arquivos Python tocados OK; `git diff --check` OK | Corrigida protecao de CSC/ID CSC: campos tratados como segredos nos formularios, valores existentes nao renderizados em HTML, novos valores criptografados, campos ampliados para 255 caracteres; NFC-e manual validada com `modelo=2`, `finalidade=1`, `operacao=1`, tentativa `nfce_emission`, webhook/reconciliacao e downloads protegidos | Validada; commit manual `8d5832fdf8cd0e4f3ad18d4a92123c7596e6391b` mantido e commit corretivo criado | Testes globais fora do alvo nao executados nesta fase; valores CSC antigos podem continuar armazenados em texto puro ate proxima edicao | Aguardar autorizacao explicita da proxima subfase |
| 2026-05-29 | 2.3.2 | Implementar e validar cancelamento padrao NFC-e | `apps/finance/models/finance.py`, `apps/finance/migrations/0047_alter_fiscaldocument_options_and_more.py`, `apps/finance/services/nfce_cancellation.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/management/commands/reconcile_webmania_documents.py`, `apps/finance/views/nfce.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfce_document_list.html`, `apps/finance/templates/finance/nfce_cancellation_form.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0047_alter_fiscaldocument_options_and_more` | 81 testes direcionados Fases 1, 2.1, 2.2A, 2.2B.1, 2.2C, 2.3.1 e 2.3.2 OK; ruff nos arquivos Python tocados OK | Cancelamento padrao usa `PUT /1/nfe/cancelar/` somente com `chave`/`uuid` e `motivo`; `nfce_referenciada` proibido; evento `cancellation`, tentativa `nfce_cancellation`, webhook/reconciliacao sem reenvio e XML de cancelamento protegido | Validada | Substituicao, contingencia/offline, inutilizacao, PDV/TEF/SAT/MFE, manifestacao, IBS/CBS, credito/debito e complementar tributaria fora do escopo | Aguardar autorizacao explicita da proxima subfase |
| 2026-05-29 | 2.3.3 | Iniciar implementacao de inutilizacao de numeracao NFC-e | `docs/fiscal-webmania/*` e codigo Fase 2.3.3 | A definir | A executar | Fase 2.3.2 validada no checkpoint `a4ae87f7e3f4748369d0d68a90d30e21a0a3d71b`; inutilizacao sera entidade propria, nao evento de NFC-e emitida; usar `PUT /1/nfe/inutilizar/` com `modelo=2` | Em implementacao | Validacao local nao cobre uso externo ao Hunter; substituicao, contingencia/offline, inutilizacao NF-e funcional e demais fases fora do escopo | Implementar e validar somente Fase 2.3.3 |
| 2026-05-29 | 2.3.3 | Implementar e validar inutilizacao de numeracao NFC-e | `apps/finance/models/finance.py`, `apps/finance/migrations/0048_alter_fiscalemissionattempt_operation_type_and_more.py`, `apps/finance/services/nfce_inutilization.py`, `apps/finance/services/fiscal_attempts.py`, `apps/finance/views/nfce.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfce_document_list.html`, `apps/finance/templates/finance/nfce_inutilization_form.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0048_alter_fiscalemissionattempt_operation_type_and_more` | Testes direcionados Fases 1, 2.1, 2.2A, 2.2B.1, 2.2C, 2.3.1, 2.3.2 e 2.3.3 OK; ruff nos arquivos Python tocados OK; `git diff --check` OK | `FiscalNumberInutilization` representa faixa, tentativa `nfce_inutilization`, body `PUT /1/nfe/inutilizar/` restrito a `modelo=2`; sem webhook/reconciliacao remota por falta de contrato oficial confirmado | Validada | Validacao local nao garante uso externo ao Hunter; `uncertain` exige decisao administrativa futura | Aguardar autorizacao explicita da proxima subfase |
| 2026-05-29 | 2.5.0 | Planejar Nota Fiscal de Credito e Nota Fiscal de Debito | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Fase 2.3.3 validada no checkpoint `08b9bf2e`; ciclo simples NFC-e encerrado. Credito/debito usam `POST /1/nfe/emissao/` com `finalidade=5/6`, tipos oficiais e dependencia IBS/CBS. Recomendado adiar codigo ate fase tributaria ou aprovacao de subconjunto seguro. | Em planejamento documental | Implementacao funcional, migrations, views, services e testes nao autorizados nesta execucao | Aguardar aprovacao para fase tributaria ou proxima subfase segura |
| 2026-05-29 | 2.4.0 | Auditar conformidade IBS/CBS NF-e/NFC-e existentes | `docs/fiscal-webmania/*`, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Webmania documenta obrigatoriedade IBS/CBS em producao para NF-e/NFC-e >= `05/01/2026`; fluxos atuais NF-e/NFC-e nao montam IBS/CBS localmente; credito/debito permanecem bloqueados ate base IBS/CBS | Aprovada documentalmente | Codigo funcional, migrations, services, views, templates e testes nao autorizados nesta execucao | Fase 2.4A+B implementada apos aprovacao |
| 2026-05-29 | 2.4A+B | Implementar base IBS/CBS e emissoes normais | `apps/finance/models/finance.py`, `apps/finance/migrations/0049_alter_taxclassnfe_options_and_more.py`, `apps/finance/services/ibs_cbs.py`, `apps/finance/services/tax_classes.py`, `apps/finance/services/nfe_emission.py`, `apps/finance/services/nfce_emission.py`, `apps/finance/forms/tax_class.py`, `apps/finance/views/tax_class.py`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0049_alter_taxclassnfe_options_and_more` | 99 testes direcionados Fases 1, 2.1, 2.2A, 2.2B.1, 2.2C, 2.3.1, 2.3.2, 2.3.3 e 2.4A+B OK; `makemigrations finance --check --dry-run` OK | Fase 2.4.0 aprovada; `TaxClassNfe` recebeu campos IBS/CBS normalizados e JSON validado; sincronizacao de classe envia `ibs_cbs`; NF-e normal e NFC-e manual bloqueiam antes do gateway sem classe IBS/CBS-ready; derivados, eventos, credito/debito, NFS-e e CT-e fora do escopo | Validada | Deploy pode bloquear NF-e/NFC-e ate classes fiscais serem configuradas com IBS/CBS valido; derivados seguem pendentes da 2.4C | Aguardar aprovacao explicita da proxima fase |
| 2026-06-02 | 2.4C.0 | Planejar documentos derivados com IBS/CBS | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Fase 2.4A+B validada no checkpoint `9eb217f2b5de2f834eb137305de1216d47e4b36e`; derivados devem usar snapshot fiscal original, NF-e externa minima fica bloqueada para parcial/complementar sem XML/importacao, ajuste exige revalidacao especifica | Em planejamento documental | Codigo funcional, migrations, services, views, templates e testes nao autorizados nesta execucao | Recomendar implementar primeiro 2.4C.1 devolucao/estorno |
| 2026-06-02 | 2.4C.1 | Implementar devolucao/estorno com IBS/CBS | `apps/finance/services/nfe_returns.py`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | Nenhuma | `makemigrations finance --check --dry-run` OK; 100 testes direcionados fiscais OK com `--keepdb`; `ruff check apps/finance/services/nfe_returns.py apps/finance/tests.py` OK; `git diff --check` OK | Fase 2.4C.0 aprovada; usar snapshot fiscal original local; `TaxClassNfe` atual nao e fallback automatico; NF-e externa minima segue bloqueada para parcial; regra conservadora IBS/CBS desde `01/01/2026` | Validada | Complementar IBS/CBS, ajuste IBS/CBS, eventos IBS/CBS, credito/debito, NFS-e e CT-e fora do escopo | Aguardar aprovacao explicita da proxima subfase |
| 2026-06-02 | 2.4C.2 | Implementar e validar complementar preco/quantidade com IBS/CBS | `apps/finance/services/nfe_complementary.py`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | Nenhuma | `makemigrations finance --check --dry-run` OK; 105 testes direcionados fiscais OK com `--keepdb`; `ruff check apps/finance/services/nfe_complementary.py apps/finance/tests.py` OK; `git diff --check` OK | Fase 2.4C.1 validada no checkpoint `c28c58afb73245d188b9ca22fe3f688e12e07f11`; usa snapshot fiscal original local em `produtos[].impostos.ibs_cbs`; `base_calculo` e obrigatorio; `TaxClassNfe` atual nao e fallback automatico; externa minima bloqueada; complementar tributaria continua fora de escopo | Validada | Ajuste IBS/CBS, eventos IBS/CBS, credito/debito, NFS-e e CT-e fora do escopo | Aguardar autorizacao explicita da proxima subfase |
| 2026-06-02 | 2.4C.3 | Proteger e validar ajuste frente a Reforma Tributaria | `apps/finance/services/nfe_adjustment.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | Nenhuma | `makemigrations finance --check --dry-run` OK; 145 testes direcionados fiscais OK com `--keepdb`; `ruff check apps/finance/services/nfe_adjustment.py apps/finance/tests.py` OK; `git diff --check` OK | Fase 2.4C.2 validada no checkpoint `11a9ba78c429936cedc7d10a5d45c6a683781be3`; contrato oficial de `/1/nfe/ajuste/` nao documenta produtos ou IBS/CBS; eventos IBS/CBS e credito/debito usam operacoes proprias; service bloqueia campos fora do contrato antes do gateway | Validada | Eventos IBS/CBS, credito/debito, complementar tributaria, NFS-e e CT-e fora do escopo | Aguardar autorizacao explicita da proxima fase |
| 2026-06-02 | 2.4D.0 | Planejar eventos IBS/CBS NF-e/NFC-e | `docs/fiscal-webmania/*`, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Fase 2.4C.3 validada no checkpoint `dd740d1fccbf692b95720a0b0de36fee1f294827`; eventos usam `POST /1/nfe/evento-ibs-cbs/` e cancelamento usa `PUT /1/nfe/evento-ibs-cbs/cancelar/`; modelar como `FiscalDocumentEvent`, nao como `FiscalDocument`; credito/debito seguem bloqueados | Documentada | Codigo funcional, migrations, services, views, templates e testes nao autorizados nesta execucao | Aguardar aprovacao explicita da Fase 2.4D.1 |
| 2026-06-02 | 2.4D.1 | Implementar evento IBS/CBS 112110 | `apps/finance/models/finance.py`, `apps/finance/migrations/0050_alter_fiscaldocumentevent_options_and_more.py`, `apps/finance/services/nfe_ibs_cbs_events.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/views/nfe.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0050_alter_fiscaldocumentevent_options_and_more` | `makemigrations finance --check --dry-run` OK; 107 testes fiscais direcionados OK com `--keepdb`; `ruff check` nos Python tocados OK; `git diff --check` OK | Fase 2.4D.0 aprovada; evento `112110` usa payload oficial estreito, `FiscalDocumentEvent(event_type=ibs_cbs)`, `FiscalEmissionAttempt(operation_type=nfe_ibs_cbs_event)`, webhook idempotente por UUID/fallback chave+sequencia, e nao altera status da NF-e/NFC-e base | Validada | Cancelamento de evento IBS/CBS, demais codigos, credito/debito, complementar tributaria, NFS-e e CT-e fora do escopo | Aguardar autorizacao explicita da proxima fase |
| 2026-06-17 | 2.4D.2 | Implementar cancelamento do evento IBS/CBS 112110 | `apps/finance/models/finance.py`, `apps/finance/migrations/0051_alter_fiscaldocumentevent_options_and_more.py`, `apps/finance/services/nfe_ibs_cbs_events.py`, `apps/finance/services/webmania_webhooks.py`, `apps/finance/views/nfe.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | `finance.0051_alter_fiscaldocumentevent_options_and_more` | `makemigrations finance --check --dry-run` OK; 161 testes fiscais direcionados OK com `--keepdb`; `ruff check` nos Python tocados OK; `git diff --check` OK | Fase 2.4D.1 validada no checkpoint `52014780a89627e7183e4a7c2eb968a8d2d9e513`; 2.4D.2 limitada a `PUT /1/nfe/evento-ibs-cbs/cancelar/` por UUID remoto do evento 112110 autorizado, com `FiscalDocumentEvent(event_type=ibs_cbs_cancellation)`, `related_event` e tentativa `nfe_ibs_cbs_event_cancellation` | Validada | Demais eventos IBS/CBS, credito/debito, complementar tributaria, NFS-e e CT-e fora do escopo | Aguardar autorizacao explicita da proxima fase |
| 2026-06-17 | 2.4D.3.0 | Planejar priorizacao dos demais eventos IBS/CBS | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Fase 2.4D.2 validada no checkpoint `dab3d559238954878259c1ad57cd503424f93d47`; revalidacao oficial indicou `112150` como menor proxima subfase por payload minimo de `data_previsao_entrega`; eventos com itens, destinatario, credito/debito e apuracao externa permanecem bloqueados | Em planejamento | Codigo funcional, migrations, services, views, templates e testes nao autorizados nesta execucao | Aguardar aprovacao explicita da Fase 2.4D.3 |
| 2026-06-17 | 2.4D.3 | Implementar evento IBS/CBS 112150 | `apps/finance/services/nfe_ibs_cbs_events.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | Nenhuma | `makemigrations finance --check --dry-run` OK; 163 testes fiscais direcionados OK com `--keepdb`; `ruff check` nos Python tocados OK | Fase 2.4D.3.0 aprovada; escopo limitado a `POST /1/nfe/evento-ibs-cbs/` com `cod_evento=112150`; revalidacao oficial confirmou `data_previsao_entrega` no topo do payload e `evento` como sequencia numerica; cancelamento do 112150 e demais eventos bloqueados | Validada | 112120/112130/112140, 211xxx, cancelamento do 112150, credito/debito, complementar tributaria, NFS-e e CT-e fora do escopo | Aguardar autorizacao explicita da proxima fase |
| 2026-06-17 | 2.4D.4 | Implementar cancelamento do evento IBS/CBS 112150 | `apps/finance/services/nfe_ibs_cbs_events.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | Nenhuma | `makemigrations finance --check --dry-run` OK; 169 testes fiscais direcionados OK com `--keepdb`; `ruff check` nos Python tocados OK | Fase 2.4D.3 validada no checkpoint `b0f2e093`; escopo limitado a `PUT /1/nfe/evento-ibs-cbs/cancelar/` para evento `112150` autorizado por UUID remoto; cancelamento `112110` permaneceu intacto | Validada | Cancelamento generico, demais eventos IBS/CBS, credito/debito, complementar tributaria, NFS-e e CT-e fora do escopo | Aguardar autorizacao explicita da proxima fase |
| 2026-06-17 | 2.4D.5.0 | Planejar eventos IBS/CBS 112120, 112130 e 112140 | `docs/fiscal-webmania/*`, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Fase 2.4D.4 validada no checkpoint `fe261d3c`; ciclo `112110`/`112150` completo. Revalidacao oficial confirmou que `112120`, `112130` e `112140` exigem `itens[]`, sequencial fiscal, valores IBS/CBS e campos de `controle_estoque`; decisao de implementar um por vez, sem fallback automatico por `TaxClassNfe` atual | Em planejamento documental | Codigo funcional, migrations, services, views, templates e testes nao autorizados; eventos `211xxx`, credito/debito, complementar tributaria, NFS-e e CT-e fora do escopo | Recomendar aprovacao futura de `2.4D.5.1` somente para `112130` isolado |
| 2026-06-18 | 2.4D.5.1 | Implementar evento IBS/CBS 112130 | `apps/finance/services/nfe_ibs_cbs_events.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*` | Nenhuma | `makemigrations finance --check --dry-run` OK; 179 testes fiscais direcionados OK com `--keepdb`; `ruff check` nos Python tocados OK; `git diff --check` OK | Fase 2.4D.5.0 aprovada; Webmania confirma `POST /1/nfe/evento-ibs-cbs/` com `cod_evento=112130` e payload `itens[]`, nao top-level `ibs_cbs`; implementacao usa `FiscalDocumentEvent(event_type=ibs_cbs, event_code=112130)` e `FiscalEmissionAttempt(operation_type=nfe_ibs_cbs_event)` | Validada | `112120`, `112140`, eventos `211xxx`, cancelamento do `112130`, credito/debito e complementar tributaria nao autorizados | Aguardar autorizacao explicita da proxima fase |
| 2026-06-18 | 2.4D.5.2 | Implementar cancelamento do evento IBS/CBS 112130 | `apps/finance/services/nfe_ibs_cbs_events.py`, `apps/finance/views/nfe.py`, `apps/finance/views/__init__.py`, `apps/finance/urls.py`, `apps/finance/templates/finance/nfe_request_detail.html`, `apps/finance/tests.py`, `docs/fiscal-webmania/*`, `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json` | Nenhuma | `makemigrations finance --check --dry-run` OK; 184 testes fiscais direcionados das Fases 1, 2.1, 2.2, 2.3, 2.4A+B, 2.4C e 2.4D ate 112130 cancelamento OK; `ruff check` nos Python tocados OK; `git diff --check` OK | Fase 2.4D.5.1 validada no checkpoint `a8a43011`; Webmania confirma cancelamento por `PUT /1/nfe/evento-ibs-cbs/cancelar/` com `uuid`, `ambiente` e `url_notificacao` opcionais/aplicaveis; implementado somente para evento `112130` autorizado, sem enviar `chave`, `cod_evento`, `evento`, `itens`, `ibs_cbs`, produtos ou credito/debito | Validada | `112120`, `112140`, eventos `211xxx`, cancelamento generico, credito/debito e complementar tributaria nao autorizados | Aguardar autorizacao explicita da proxima fase |
| 2026-06-18 | 2.4D.6.0 | Planejar decisao final para eventos IBS/CBS 112120 e 112140 | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check -- docs/fiscal-webmania` OK | Fase 2.4D.5.2 validada no checkpoint `d7a82117`; ciclo completo validado para `112110`, `112150` e `112130`. Revalidacao oficial confirmou `112120` como importacao ALC/ZFM nao convertida em isencao e `112140` como nao fornecimento com pagamento antecipado; ambos exigem `itens[]`, sequencial fiscal, valores IBS/CBS e `controle_estoque` | Documentada | Codigo funcional, migrations, services, views, templates e testes nao autorizados; eventos `211xxx`, credito/debito, complementar tributaria, NFS-e e CT-e fora do escopo | Recomendar adiar ambos e aprovar fase preparatoria de importacao XML/snapshot fiscal e/ou credito-debito/pagamento antecipado |
| 2026-06-19 | 2.4D.6.0 | Registrar aprovacao da decisao final | `docs/fiscal-webmania/*` | Nenhuma | Documental | `112120` e `112140` adiados; `112110`, `112130` e `112150` possuem ciclos completos; cancelamento nao sera generalizado; `211xxx` adiados | Aprovada | Dependencias locais permanecem ausentes | Replanejar credito/debito |
| 2026-06-19 | 2.5.1.0 | Replanejar NF-e de credito/debito apos IBS/CBS | `docs/fiscal-webmania/*`, OpenAPI validado | Nenhuma | `git diff --check -- docs/fiscal-webmania` OK; OpenAPI JSON parseado com sucesso | Contrato oficial revalidado: enums 1-5/1-8; credito usa `nfe_referenciada`; debito 3/4 usa `produtos[].dfe_referenciado`; itens enviam somente IBS/CBS e CFOP na raiz. Auditoria nao encontrou fonte local completa para nenhum tipo. | Documentada, aguardando aprovacao | Nenhum codigo funcional autorizado | Recomendar Fase 2.5.1P preparatoria |
| 2026-06-19 | 2.5.1P | Iniciar preparacao da base fiscal referenciada | `docs/fiscal-webmania/*` e codigo restrito da Fase 2.5.1P | A definir | A executar | Fase 2.5.1.0 aprovada; todos os tipos de credito/debito adiados. Preparar somente documento/item, snapshot IBS/CBS, hipotese, vinculos e habilitacao por oficina. | Em implementacao | Emissao credito/debito, 112120/112140, 211xxx e demais fases bloqueadas | Auditar arquitetura real e implementar base minima |
| 2026-06-19 | 2.5.1P | Implementar e validar base fiscal referenciada | Models, service, form, views, URLs, templates, testes e `docs/fiscal-webmania/*` | `finance.0052_webmaniacompany_credit_debit_basis_enabled_and_more` | 192 testes fiscais direcionados OK; 13 testes focados finais; makemigrations/ruff/diff check OK | `FiscalReferencedBasis`, snapshot historico imutavel, referencias financeira/estoque opcionais, flag auditada e quatro permissoes; sem gateway, documento ou tentativa de credito/debito | Validada | Hipoteses continuam sem fonte suficiente para emissao automatica; documento externo exige XML validado | Aguardar autorizacao explicita da proxima fase |
| 2026-06-19 | 2.5.1P | Registrar encerramento aprovado | Checkpoint `f199905d` | `finance.0052` | Validacoes aprovadas | Base fiscal referenciada validada; emissao permanece bloqueada | Validada e encerrada | Nenhuma | Planejar primeiro tipo |
| 2026-06-19 | 2.5.2.0 | Selecionar primeiro tipo de credito/debito | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Todos os tipos reavaliados; credito tipo 1 e o menor candidato, mas falta base monetaria/comercial por item | Documentada | Nenhum codigo funcional autorizado | Recomendar Fase 2.5.2P preparatoria |
| 2026-06-19 | 2.5.2.0 | Registrar aprovacao da decisao | `docs/fiscal-webmania/*` | Nenhuma | Documental | Opcao D aprovada; credito tipo 1 permanece candidato futuro | Aprovada | Emissao continua bloqueada | Implementar somente base preparatoria 2.5.2P |
| 2026-06-19 | 2.5.2P | Iniciar base monetaria e comercial por item | `docs/fiscal-webmania/*` e codigo restrito da Fase 2.5.2P | A definir | A executar | Congelar quantidade, unidade, valores, CFOP, snapshots e composicao monetaria sem transmissao remota | Em implementacao | Nenhum gateway, `FiscalDocument` de credito/debito ou `FiscalEmissionAttempt` autorizado | Auditar fontes e implementar base minima |
| 2026-06-19 | 2.5.2P | Implementar, revisar e validar base monetaria/comercial | `apps/finance/models/finance.py`, `apps/finance/models/__init__.py`, `apps/finance/services/fiscal_referenced_basis.py`, `apps/finance/forms/fiscal_referenced_basis.py`, `apps/finance/views/fiscal_referenced_basis.py`, templates da base, `apps/finance/test_fiscal_referenced_basis.py`, `docs/fiscal-webmania/*` | `finance.0053_fiscalreferencedbasisitem` | 204 testes fiscais direcionados OK; 24 testes focados finais; makemigrations, ruff e diff check OK | `FiscalReferencedBasisItem` one-to-one, Decimal, extracao historica conservadora, composicao explicita, rascunho incompleto e imutabilidade integral apos aprovacao; sem gateway/tentativa/documento remoto | Validada | Bases antigas nao recebem backfill; emissao segue bloqueada | Aguardar aprovacao do checkpoint e nova autorizacao |
| 2026-06-22 | 2.5.2P | Registrar encerramento aprovado | Checkpoint `638d4c12` | `finance.0053` | Validacoes aprovadas | Base monetaria/comercial e snapshots imutaveis validados; composicao multa + juros confirmada localmente | Validada e encerrada | Nenhuma emissao | Planejar credito tipo 1 |
| 2026-06-22 | 2.5.3.0 | Planejar emissao NF-e credito tipo 1 | `docs/fiscal-webmania/*` | Nenhuma | `git diff --check -- docs/fiscal-webmania` | Contrato oficial revalidado; base local pronta, mas valoracao do produto e IBS/CBS de multa/juros nao documentados com seguranca | Documentada, aguardando aprovacao | Emissao continua bloqueada | Recomendar Fase 2.5.3P de validacao fiscal |
| 2026-06-22 | 2.5.3.0 | Registrar aprovacao da decisao | `docs/fiscal-webmania/*` | Nenhuma | Documental | Adiar credito tipo 1; nao assumir quantidade 1, nao copiar item integral e nao recalcular IBS/CBS | Aprovada | Nenhuma transmissao | Implementar somente preview 2.5.3P |
| 2026-06-22 | 2.5.3P | Iniciar validacao do produto multa/juros | `docs/fiscal-webmania/*` e codigo restrito da 2.5.3P | A definir | A executar | Pre-payload auditavel com valores administrativos explicitos e IBS/CBS historico, sem gateway | Em implementacao | Emissao/documento/tentativa remotos proibidos | Implementar e validar preview interno |
| 2026-06-22 | 2.5.3P | Implementar preview fiscal local | Model, service, form, views, URLs, templates, testes e `docs/fiscal-webmania/*` | `finance.0054_fiscalcreditproductpreview` | 41 testes focados OK; makemigrations e ruff OK; suite ampla pendente | Preview versionado, valores explicitos, total=multa+juros, IBS/CBS historico, grupos proibidos bloqueados, UI/permissoes; sem gateway | Implementada, em validacao final | Emissao continua bloqueada | Executar suite fiscal completa e checkpoint |
| 2026-06-22 | 2.5.3P | Validar preview fiscal local | Mesmo escopo da implementacao | `finance.0054_fiscalcreditproductpreview` | 221 testes fiscais direcionados OK; 41 testes focados OK; makemigrations, ruff e diff check OK | Auto-revisao corrigiu lock PostgreSQL em relacao reversa e validacao de listas JSON vazias; nenhum gateway/documento/tentativa remota | Validada | Regra ainda nao autoriza transmissao fiscal | Criar checkpoint e aguardar aprovacao |
| 2026-06-22 | 2.5.4 | Iniciar emissao NF-e credito tipo 1 | `docs/fiscal-webmania/*` e codigo restrito da 2.5.4 | A definir | A executar | Consumir somente preview aprovada; `modelo=1`, `finalidade=5`, `tipo_credito=1`; somente IBS/CBS | Em implementacao | Debito, outros creditos e cancelamento permanecem bloqueados | Auditar extensoes existentes e implementar fluxo idempotente |
| 2026-06-22 | 2.5.4 | Implementar e validar emissao NF-e credito tipo 1 | Model, migration, service, webhook, reconciliacao, views, URLs, template, testes e PRDs | `finance.0055_alter_fiscaldocument_options_and_more` | 231 testes fiscais direcionados OK; 12 testes da fase OK; makemigrations, Ruff e diff check OK | Preview exclusiva; somente IBS/CBS; documento/link/tentativa antes do HTTP; timeout uncertain; lock PostgreSQL restrito a preview; quatro asserts preparatorios atualizados para ausencia de efeitos remotos | Validada tecnicamente | Cancelamento, debito e tipos 2-5 bloqueados | Criar checkpoint e aguardar nova autorizacao |
| 2026-06-22 | 2.5.5 | Iniciar cancelamento NF-e credito tipo 1 | `docs/fiscal-webmania/*` e codigo restrito da 2.5.5 | A definir | A executar | Fase 2.5.4 validada no checkpoint `a79f6b7f`; cancelamento padrao NF-e por chave/UUID e motivo, sem payload de emissao ou evento IBS/CBS | Em implementacao | Debito, tipos 2-5 e demais fases bloqueados | Reutilizar evento/tentativa do cancelamento NFC-e com escopo proprio |
| 2026-06-22 | 2.5.5 | Implementar e validar cancelamento NF-e credito tipo 1 | Model choices/permissao, migration, service, webhook, reconciliacao, views, URLs, template, testes e PRDs | `finance.0056_alter_fiscaldocument_options_and_more` | 246 testes fiscais direcionados OK; 25 testes emissao/cancelamento OK; 13 testes especificos OK; makemigrations, Ruff e diff check OK | `PUT /1/nfe/cancelar/` somente chave/UUID e motivo; evento cancellation; tentativa nfe_credit_cancellation; timeout uncertain; webhook ambiguo bloqueado; origem/base/preview imutaveis | Validada tecnicamente | Debito, tipos 2-5, 112120/112140, 211xxx e demais fases bloqueados | Criar checkpoint e aguardar nova autorizacao |

## Detalhes da Fase 1 - 2026-05-28

### Implementado

- Criado `FiscalEmissionAttempt` como idempotencia persistida por `workshop`, tipo documental e chave de intencao.
- Criados estados de tentativa: `created`, `sent`, `succeeded`, `failed`, `uncertain`.
- NF-e e NFS-e criam e bloqueiam tentativa antes da chamada HTTP remota.
- Timeout ou resposta remota invalida apos envio marcam tentativa como `uncertain`.
- Tentativa `uncertain` bloqueia reenvio automatico da mesma intencao.
- Payload de tentativa e respostas sao persistidos de forma sanitizada, sem headers ou credenciais.
- Webhook Webmania recebeu fingerprint persistido, constraint unica compatível e processamento idempotente.
- Webhook duplicado nao duplica efeitos; evento fora de ordem nao regride status.
- Webhook com UUID ambiguo entre oficinas fica pendente sem atualizar documento de outra oficina.
- Reconciliação operacional consulta NF-e, NFS-e e tentativas `uncertain`, sem emitir.
- Prints/debugs fiscais foram substituidos por logging sanitizado.
- NF-e passou a usar permissao `nferequest` com fallback temporario para `nfserequest`.

### Evidencias fiscais

| Risco | Evidencia |
| ----- | --------- |
| Concorrencia/duplicidade | `FiscalPhaseOneConcurrentEmissionTests.test_concurrent_nfe_emission_intention_calls_remote_once` passou e valida duas threads simultaneas com uma chamada remota. O teste sequencial `FiscalPhaseOneStabilizationTests.test_duplicate_nfe_intention_calls_remote_once_and_sanitizes_payload` tambem passou. |
| Timeout uncertain | `FiscalPhaseOneStabilizationTests.test_nfe_timeout_marks_uncertain_and_blocks_resend` passou e valida status `uncertain`. |
| `uncertain` bloqueia reenvio | Mesmo teste valida que a segunda chamada nao chama `requests.post`. |
| Webhook duplicado | `FiscalPhaseOneStabilizationTests.test_webhook_duplicate_is_idempotent_and_out_of_order_status_does_not_regress` passou. |
| Webhook fora de ordem | Mesmo teste valida que status aprovado nao regride para processando. |
| Reconciliação NFS-e sem emissão | `FiscalPhaseOneStabilizationTests.test_reconciliation_command_consults_nfse_without_emitting` passou. |
| Isolamento entre oficinas | `FiscalPhaseOneStabilizationTests.test_webhook_ambiguous_uuid_is_deferred_without_cross_workshop_update` passou. |
| Permissao legada preservada | `FiscalPhaseOneStabilizationTests.test_workshop_permission_fallback_preserves_legacy_nfe_permission` passou. |
| Ausencia de credenciais em logs/payload | Teste de duplicidade valida sanitizacao de `token`, `secret` e `headers`. |

### Comandos obrigatorios executados

| Comando | Resultado |
| ------- | --------- |
| `uv run python manage.py makemigrations --check --dry-run` | Falhou por migrations pendentes nao fiscais em `customer`, `scheduling`, `suppliers`. |
| `uv run python manage.py migrate --plan` | OK; planeja `finance.0041_fiscalemissionattempt_and_more`. |
| `uv run python manage.py test apps.finance --keepdb` | Falhou em `DreReportViewTests.test_dre_workorder_cost_total_includes_kit_service_cost`; o mesmo teste isolado falha no baseline anterior a Fase 1 com `Money('90.00') != Money('145.00')`. |
| `uv run python manage.py test apps.workshops --keepdb` | Falhou em testes de arquivo/logo/certificado Webmania, fora do escopo da Fase 1. |
| `uv run python manage.py test apps.workorder --keepdb` | Falhou em testes de OS/reabertura/assinatura/filtros, fora do escopo da Fase 1. |
| `uv run ruff check .` | Falhou por imports F401 preexistentes em `movement_group.py`, `workorder/reopening.py`, `workorder/views.py`. |
| `uv run mypy .` | Falhou com erros amplos preexistentes de stubs/tipos; branch atual mediu 2755 erros em 216 arquivos contra baseline medido de 2756 erros em 216 arquivos. |

## 2026-06-22 - Fase 2.5.6.0 - Reavaliacao documental

- Fase 2.5.5 reconhecida como validada no checkpoint `5d612544`.
- Registrado ciclo completo do credito tipo 1: base fiscal, base comercial/monetaria, preview, emissao e cancelamento.
- Revalidada documentacao oficial para creditos 1-5, debitos 1-8, `dfe_referenciado`, exclusividade IBS/CBS e eventos pendentes.
- Comparados credito 2-5, debito 4/6/7, `112120`, `112140`, `211xxx`, NFS-e e CT-e.
- Decisao recomendada: Fase 2.5.6P preparatoria para preview fiscal propria de debito tipo 4, sem transmissao.
- OpenAPI validado revisado e considerado suficiente; nenhum schema alterado.
- Planejamento encerrado como documentado e aguardando aprovacao da Fase 2.5.6P.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.

## 2026-06-23 - Fechamento da Fase 3.1

- Criados `NfseMunicipalCapability`, flag `WebmaniaCompany.nfse_legacy_compatibility_enabled` e campos `remote_updated_at` em lote/item pela migration `0060`.
- Emissao legada valida capacidade e requisitos municipais antes do gateway; ausencia de capacidade preserva o legado somente sob flag explicita.
- Webhook/consulta usam payload sanitizado, `atualizado_em` canonico e anti-regressao por timestamp/rank.
- Reconciliacao confirmada como somente consulta por UUID, sem reemissao, cancelamento, substituicao ou manifestacao.
- Validacao: `makemigrations finance --check --dry-run` OK; Ruff dos Python tocados OK; 13 testes NFS-e 3.1 OK; 297 testes fiscais direcionados OK; `git diff --check` OK.
- Status: validada; fases 3.2 e posteriores nao iniciadas.

## 2026-06-23 - Inicio da Fase 3.2

- Fase 3.1 validada no checkpoint `3901cf9325864663412af29e72a98d9500907b15`.
- Auditados `NfseRequest`, `NfseBatch`, `NfseItem`, `NfseMunicipalCapability`, consulta, webhook, reconciliacao, UI e testes da 3.1.
- Contrato Webmania NFS-e v3.1.1 revalidado: `GET /2/nfse/consulta/{uuid}` retorna `modelo=nfse|lote_rps`; `GET /2/nfse/status` retorna capacidades do provedor; `atualizado_em` permanece referencia canonica.
- Escopo autorizado: somente consulta/reconciliacao de item/lote/status municipal. Cancelamento, substituicao, manifestacao e emissao manual nova permanecem bloqueados.

## 2026-06-23 - Fechamento da Fase 3.2

- Implementados GET por UUID para `NfseItem`/`NfseBatch`, reconciliacao de `info_nfse`, snapshot `/2/nfse/status`, auditoria de origem e permissões especificas.
- Corrigidos durante auto-revisao: lock PostgreSQL sobre FK nullable; remapeamento duplo de item no webhook de lote; lote ausente no comando; compatibilidade de query legada sem empresa/permissao nova.
- Migration `0061_alter_nfsemunicipalcapability_options_and_more` sem alteracao destrutiva ou backfill.
- Validacao: 14 testes 3.2 OK; 2 testes legados de consulta OK; 311 testes fiscais direcionados OK; migration-check, Ruff e diff-check OK.
- Status: validada; cancelamento idempotente, substituicao, manifestacao e emissao manual nova nao iniciados.

## 2026-06-23 - Inicio da Fase 3.3

- Fase 3.2 validada no checkpoint `ad93e87308959d9f4b0f6fc69cfa9ec83c45b428`.
- Cancelamento legado auditado: PUT direto em `emission.py`, permissao generica, sem tentativa persistida, concorrencia ou `uncertain`.
- Escopo autorizado: somente cancelamento idempotente de `NfseItem` legado; lote, NFS-e original relacionada e demais operacoes nao podem ser alterados.
- Substituicao, manifestacao, emissao manual nova e projecao generalizada `FiscalDocument(nfse)` permanecem bloqueadas.

## 2026-06-23 - Fechamento tecnico da Fase 3.3

- Criados `NfseCancellation`, permissao `cancel_nfse` e `FiscalEmissionAttempt(operation_type="nfse_cancellation")`.
- PUT restrito a `{uuid, motivo}`; timeout e resposta inconclusiva reservam a intencao como `uncertain` sem reenvio.
- Webhook confirma somente UUID nao ambiguo, respeita `atualizado_em` e preserva o XML original; reconciliacao usa apenas GET.
- Auto-revisao corrigiu lock com join anulavel, separacao do XML de cancelamento e historico com unicidade condicional para permitir nova intencao somente apos falha conclusiva.
- Validacao: 14 testes 3.3, 219 testes fiscais existentes e 104 testes equivalentes de credito/debito aprovados; migration-check, Ruff e diff-check aprovados. Mypy manteve erros de baseline preexistentes fora do escopo.
- Substituicao, manifestacao, emissao manual nova, CT-e, MDF-e, NFCom e DC-e nao iniciados.

## 2026-06-23 - Fase 3.4.0 documental

- Fase 3.3 validada no checkpoint `401b6553302ae1250a5b8838c77a43fa32ef9daa`; cancelamento idempotente, XML separado e `uncertain` sem reenvio confirmados.
- Revalidado `POST /2/nfse/substituir`: tabela/exemplo exigem `ambiente`, `codigo_verificacao`, motivo `1/2/4` e novo `rps`; resposta retorna substituta e objeto `nfse_substituida`.
- Identificada inconsistencia oficial: texto introdutorio cita `uuid`, mas tabela/exemplo nao o enviam. O OpenAPI validado permanece alinhado a tabela/exemplo e nao foi alterado.
- Decisao: Opcao B, criar Fase 3.4P para preview imutavel do novo RPS sem transmissao. Substituicao funcional, manifestacao e emissao manual nova nao iniciadas.

## 2026-06-23 - Inicio da Fase 3.1

- Fase 3.0 aprovada; autorizada somente estabilizacao do legado NFS-e.
- Regra de rollout: capacidade aplicavel prevalece; sem capacidade, o legado funciona apenas com compatibilidade explicita ativa na empresa.
- Escopo tecnico: model de capacidade, validacao pre-gateway, timestamp remoto `atualizado_em`, reconciliacao nao emissora, permissao/UI e testes.
- Cancelamento idempotente, substituicao, manifestacao, emissao manual e `FiscalDocument(nfse)` permanecem proibidos.

## 2026-06-23 - Fase 3.0 - Auditoria e planejamento NFS-e expandida

- Fase 2.6.0 reconhecida como aprovada; NFS-e expandida priorizada sem autorizacao funcional.
- Auditados models, configuracao, emissao, RPS/lote, consulta, cancelamento, webhook, reconciliacao, UI, downloads, permissoes e testes NFS-e atuais.
- Revalidada Webmania NFS-e v3.1.1: Bearer v2, `/status`, emissao, consulta por UUID, cancelamento/agendamento, substituicao, manifestacao Padrao Nacional, downloads e webhook com `atualizado_em`.
- Revalidada a documentacao de producao do Padrao Nacional, incluindo manuais de contribuinte, APIs ADN e anexos DPS/NFS-e/eventos.
- Decidida convivencia gradual do legado com projecao `FiscalDocument` sob demanda e capacidade municipal separada.
- Roadmap 3.1-3.7 definido; primeira fase funcional recomendada: 3.1.
- OpenAPI corrigido para substituicao, manifestacao, status municipal, agendamento e `atualizado_em`.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.

## 2026-06-22 - Inicio da Fase 2.5.6P

- Fase 2.5.6.0 aprovada; debito tipo 4 selecionado como proximo candidato.
- Auditoria confirmou base/item e snapshots reutilizaveis, mas preview de credito semanticamente imutavel e nao reutilizavel.
- Decidido reutilizar somente `credit_debit_basis_enabled` como flag preparatoria geral; permissoes e preview de debito serao proprias.
- Emissao de debito e qualquer chamada Webmania permanecem bloqueadas.

## 2026-06-22 - Implementacao e validacao da Fase 2.5.6P

- Criado `FiscalDebitProductPreview`, migration `0057_fiscaldebitproductpreview.py`, service local, form, views, URLs e templates.
- Reutilizada somente a flag preparatoria geral; criadas quatro permissoes especificas de preview de debito.
- Pre-payload congela `finalidade=6`, `tipo_debito=4`, `dfe_referenciado`, produto, CFOP, valores e somente IBS/CBS.
- Auto-revisao confirmou ausencia de gateway, `FiscalDocument` de debito e `FiscalEmissionAttempt` de debito.
- Correcao durante validacao: teste ajustado para comprovar que o enum/documento de debito sequer foi aberto.
- Validacoes: 14 testes novos, 80 regressivos diretos e 260 fiscais dirigidos passaram; migrations, Ruff e diff aprovados.

## 2026-06-22 - Fase 2.5.7.0 - Planejamento final debito tipo 4

- Fase 2.5.6P reconhecida como validada no checkpoint `189bf973`.
- Contrato Webmania revalidado para `finalidade=6`, `tipo_debito=4`, `dfe_referenciado` por produto, CFOP na raiz e IBS/CBS exclusivo.
- Decidido nao enviar `nfe_referenciada` no debito tipo 4.
- Matriz confirmou todas as fontes fiscais e monetarias; faltam somente flag e permissoes de emissao, que pertencem a fase funcional.
- Recomendado implementar debito tipo 4 como proxima fase, restrito a origem local e preview aprovada.
- Cancelamento mantido em fase posterior pelo fluxo NF-e padrao.
- OpenAPI revisado e considerado suficiente; nenhum arquivo de API alterado.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.

## 2026-06-22 - Inicio da Fase 2.5.7

- Fase 2.5.7.0 aprovada para implementar somente debito tipo 4, multa/juros e origem local.
- Emissao deve partir exclusivamente de `FiscalDebitProductPreview` aprovada.
- `nfe_referenciada`, tributos tradicionais, outros tipos, cancelamento e eventos permanecem proibidos.
- Implementacao deve reutilizar infraestrutura segura do credito sem compartilhar intencao, permissao, flag ou documento.

## 2026-06-22 - Implementacao e validacao tecnica da Fase 2.5.7

- Criados service/UI de emissao, migration `0058`, flag auditavel e quatro permissoes especificas.
- Implementados documento `debit`, link `debits`, tentativa `nfe_debit_emission`, webhook, reconciliacao por consulta e downloads protegidos.
- Auto-revisao endureceu coerencia da origem local, chave, snapshots, composicao multa+juros, valores congelados e ambiguidade global do webhook.
- Tres testes preparatorios antigos foram atualizados: o operation type agora existe, mas preparar base/preview continua sem criar documento ou tentativa.
- Validacoes: 16 testes especificos e 276 testes fiscais dirigidos passaram; migration, Ruff e diff aprovados.
- Cancelamento, outros debitos, creditos 2-5 e demais blocos permaneceram nao iniciados.

## 2026-06-22 - Inicio da Fase 2.5.8

- Fase 2.5.7 validada no checkpoint `9214150d`.
- Autorizado somente cancelamento da NF-e de debito tipo 4 pelo endpoint NF-e padrao.
- Contrato oficial revalidado: identificador e motivo no body; ambiente e dados de emissao nao sao enviados.
- Decidida operacao propria `nfe_debit_cancellation`, sem reutilizar cancelamento de evento IBS/CBS.
- Demais debitos, creditos 2-5 e demais fases permanecem bloqueados.

## 2026-06-22 - Implementacao e validacao tecnica da Fase 2.5.8

- Criados service de cancelamento, views, rotas, UI, migration `0059` e permissao `cancel_nfe_debit`.
- Implementados evento `nfe_debit_cancellation`, tentativa homonima, webhook seguro e reconciliacao por consulta.
- Auto-revisao confirmou body estrito, status cancelado somente com confirmacao remota e imutabilidade da nota original/base/preview.
- Ajustes durante testes: mocks passaram a respeitar unicidade global de UUID de evento e assercoes comprovaram valor sensivel redigido em vez de ocultar o nome da chave.
- Validacoes: 10 testes especificos, 51 cruzados e 286 fiscais dirigidos passaram; migration, Ruff e diff aprovados.
- Outros debitos, creditos 2-5, eventos pendentes e demais fases nao foram iniciados.

## 2026-06-23 - Fase 2.6.0 - Reavaliacao documental do roadmap

- Fase 2.5.8 reconhecida como validada no checkpoint `df1a163e`.
- Registrados os ciclos completos do credito tipo 1, debito tipo 4 e eventos IBS/CBS `112110`, `112130` e `112150`.
- Revalidados contratos oficiais de NF-e/NFC-e, NFS-e, CT-e, MDF-e, NFCom e DC-e.
- Comparados creditos 2-5, debitos 1-3/5-8, `112120`, `112140`, `211xxx`, complementar tributaria e demais familias.
- Decisao recomendada: iniciar Fase 3.0 documental de auditoria e planejamento NFS-e expandida.
- Corrigida a classificacao oficial de NFCom/DC-e para API v2.0.0; flags administrativas permanecem como politica interna.
- Nenhum codigo funcional, migration, service, view, template ou teste foi alterado.
