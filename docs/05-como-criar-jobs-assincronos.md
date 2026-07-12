# Como Criar e Gerenciar Jobs Assíncronos (Hunter v2)

Este documento descreve como criar, enfileirar e monitorar tarefas pesadas fora do request web, utilizando a nossa infraestrutura baseada em Celery e o modelo `BackgroundJob`.

## A Estrutura Base

Nossa arquitetura de jobs possui duas peças fundamentais:
1. **O Modelo `BackgroundJob`** (banco de dados): Armazena o estado da tarefa (pendente, processando, concluído, falhou), quem pediu, quando começou/terminou, além do payload (JSON com parâmetros de entrada) e o resultado/erro.
2. **A Classe `HunterBackgroundJobTask`** (Celery): Uma classe base que envolve a sua lógica de negócio, garantindo *idempotência*, *atualização de status*, *timeouts*, *retries (com backoff)* e *dead-letter* automáticos.

## Passo a Passo para Criar um Novo Job

### 1. Defina a Tarefa (Task)

Em qualquer arquivo `tasks.py` da sua app (por exemplo, `apps/finance/tasks.py`), importe a classe base e crie a sua tarefa usando o decorator `@shared_task`:

```python
from celery import shared_task
from apps.core.infrastructure.tasks import HunterBackgroundJobTask
from apps.core.infrastructure.models import BackgroundJob

@shared_task(
    bind=True, 
    base=HunterBackgroundJobTask, 
    max_retries=3,          # Quantas vezes tentar de novo se der erro?
    soft_time_limit=120     # Timeout da tarefa em segundos
)
def generate_fiscal_zip_task(self: HunterBackgroundJobTask, job_id: str):
    # 1. Buscamos o job no banco
    job = BackgroundJob.objects.get(pk=job_id)
    
    # 2. Lemos os parâmetros que a view passou
    start_date = job.payload.get("start_date")
    end_date = job.payload.get("end_date")
    
    # 3. Executamos a lógica pesada
    zip_url = make_heavy_zip(job.workshop_id, start_date, end_date)
    
    # 4. Retornamos o resultado. O HunterBackgroundJobTask vai 
    # salvar isso no campo `job.result` e mudar o status para COMPLETED.
    return {"status": "success", "download_url": zip_url}
```

### 2. Dispare a Tarefa (View / Service)

Na sua view ou service, ao invés de rodar o código pesado na hora, você cria o modelo no banco de dados e joga para a fila:

```python
from apps.core.infrastructure.models import BackgroundJob

def request_zip_generation(request, workshop):
    # 1. Crie o registro no banco (Pendente)
    job = BackgroundJob.objects.create(
        job_type="generate_fiscal_zip",
        workshop=workshop,
        requested_by=request.user,
        payload={
            "start_date": "2023-01-01",
            "end_date": "2023-01-31"
        },
        correlation_id=f"zip-{workshop.id}-202301" # Evita gerar o mesmo zip duplicado se clicar 2x
    )
    
    # 2. Mande para a fila do Celery (.delay manda pro RabbitMQ na hora)
    generate_fiscal_zip_task.delay(job_id=str(job.id))
    
    return {"message": "Sua requisição está na fila! ID: " + str(job.id)}
```

## Tratamentos Automáticos

Você não precisa escrever código para tratar o ciclo de vida. A classe base faz isso:
* **Idempotência:** Se o `BackgroundJob` já estiver `completed` ou `cancelled`, o Celery não vai processar de novo.
* **Timeout (`soft_time_limit`):** Se a tarefa travar (ex: API da Webmania caiu) por mais de X segundos, ela é morta, o job ganha o status `failed` com o erro "Timeout", e não trava os workers.
* **Retry Inteligente:** Se der erro de rede, o job volta pro status `pending` e entra num retry exponencial. Na última tentativa (`max_retries`), o status muda de vez para `failed` (Dead-letter final).
* **Correlation ID:** Use para agrupar tentativas ou evitar a criação do mesmo Job em requests repetidos.
