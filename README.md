# Simulación de Tráfico Auto-Organizado (SOTL) mediante Net Interactions

Este proyecto es un entorno de simulación computacional desarrollado en Python que modela una red de semáforos inteligentes. Utiliza la teoría de **Net Interactions** y el algoritmo **SOTL (Self-Organizing Traffic Lights)** para demostrar cómo un sistema descentralizado puede autoorganizarse y optimizar el flujo vehicular frente a eventos estocásticos, como accidentes de tráfico.

## 🧠 Fundamento Teórico

El núcleo de la simulación prescinde de controladores centrales o tiempos de ciclo fijos. En su lugar, cada semáforo opera como un agente autónomo que toma decisiones basándose en la demanda local y la interacción con sus nodos adyacentes.

### Algoritmo SOTL
La decisión de cambiar la fase del semáforo (de rojo a verde) se rige por la acumulación de vehículos y el tiempo de espera. La transición ocurre cuando la "presión" local supera un umbral empírico $\theta$. Matemáticamente, la evaluación se define como:

$\kappa = \sum_{i=1}^{n} w_i \cdot t_i \ge \theta$

Donde:
* $n$: Número de vehículos esperando en la intersección.
* $w_i$: Peso o prioridad del vehículo $i$ (por defecto = 1).
* $t_i$: Tiempo que el vehículo $i$ lleva esperando frente a la luz roja.

### Teoría de Net Interactions
La red alcanza la estabilidad a través de interacciones emergentes. Cuando un evento estocástico (accidente) reduce la capacidad de una vía, la acumulación de vehículos dispara el umbral $\theta$ más rápidamente en los nodos previos. Esto propaga la información de congestión en sentido inverso al flujo vehicular, forzando a la red a reequilibrar sus tiempos de verde sin necesidad de una comunicación explícita de la falla.

## 🏗️ Arquitectura del Proyecto

El sistema está diseñado con una arquitectura modular orientada a objetos, separando la topología de la red, la lógica de los agentes y el motor de renderizado.



1.  **Lógica de Agentes (`SemaforoSOTL`)**: Encapsula el estado de cada intersección y evalúa continuamente la ecuación de decisión en cada *tick* de simulación.
2.  **Entorno y Grafo (`Calle`, `SimulacionSOTL`)**: Maneja la física básica de la red, la inyección de eventos aleatorios (accidentes guiados por una probabilidad $p$ cada tiempo $t$) y la actualización del estado global.
3.  **Renderizado Visual (`pygame`)**: Desacoplado de la lógica de negocio, se encarga exclusivamente de la representación gráfica del grafo en tiempo real a 60 FPS.
4.  **Topología Externa (JSON)**: La configuración de las calles y nodos se inyecta mediante archivos externos, permitiendo probar la escalabilidad del algoritmo en redes de distinta complejidad.

## ⚙️ Requisitos e Instalación

El proyecto requiere Python 3.8+ y la librería Pygame para la visualización.

```bash
# Clonar el repositorio
git clone <url-del-repositorio>
cd simulacion-sotl

# Crear y activar un entorno virtual (opcional pero recomendado)
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install pygame