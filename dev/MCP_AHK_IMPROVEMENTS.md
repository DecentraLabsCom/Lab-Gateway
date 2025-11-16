# Bayesian Edge Agent for GUI Resilience in Remote Lab Gateways

## Overview
This project extends the **DecentraLabs Lab Gateway** with a **Bayesian edge agent** that ensures resilient and autonomous operation of GUI-based remote laboratories. The agent perceives the GUI state, reasons under uncertainty, and acts deterministically through a standardized tool layer (**MCP**) and **AutoHotkey (AHK)** macros.  

The goal is to transform fragile remote desktop sessions into **self-healing services**, reducing downtime, increasing energy efficiency, and enabling seamless access to online laboratories for students, researchers, and institutions across Europe.

---

## Motivation
Remote labs rely heavily on GUIs to interact with scientific and engineering applications. Current approaches to automation face major limitations:
- **Fixed scripts** are brittle; unexpected pop-ups, focus loss, or timeouts break them.  
- **RPA tools** are powerful but heavy, cloud-dependent, and unsuitable for edge environments.  
- **Manual intervention** leads to high support costs and poor user experience.  

Our approach introduces **probabilistic reasoning** into GUI automation, allowing the system to handle uncertainty and act robustly in real time on **low-cost edge hardware**.

---

## New Functionalities

### 1. Bayesian GUI State Estimation
- The agent models GUI operation as a **partially observable process** with hidden states:  
  - `ok`, `modal`, `timeout`, `disconnected`.
- Observations come from:  
  - Window/title events  
  - Lightweight bitmap probes  
  - Telemetry (CPU, RAM, network)  
- A **Bayesian filter** estimates the belief distribution over hidden states, enabling reasoning under uncertainty.

### 2. Deterministic Actuation via MCP + AutoHotkey
- **MCP (Model Context Protocol)** exposes standardized tools for session management.  
- Each tool maps to a deterministic **AutoHotkey (AHK) macro** on the provider PC.  
- Actions include: dismissing pop-ups, restoring focus, restarting applications, or reinitializing a session.  
- Policies are **lab-invariant**, while per-lab actuation is encapsulated in **AHK profiles**.

### 3. Edge-Optimized Implementation
- The agent runs on **Jetson or Raspberry Pi** devices colocated with the gateway.  
- Optimizations include:  
  - Adaptive polling  
  - Lock-free queues  
  - Incremental bitmap probes  
  - Optional CUDA kernels for performance-critical paths  
- Profiling ensures **latency, energy, and memory budgets** are met on constrained hardware.

### 4. Fault Injection and Recovery
- A test harness injects GUI faults (modals, focus theft, delays).  
- The agent recovers autonomously, compared against a scripted baseline.  
- KPIs:  
  - ≥2× faster recovery latency  
  - ≥30% energy efficiency gains  
  - ≤5% accuracy deviation  

### 5. Natural Language GUI Control
- **MCP-Mediated Language Interface** connects language models to laboratory GUI operations through standardized tools.
- Users can issue complex commands in natural language, such as:
  - *"Start the experiment, introduce a 3-volt step input, configure the PID with Kp=2.5, Ki=0.8, Kd=0.1, and measure for 30 seconds before saving the data"*
  - *"Switch to oscilloscope mode, set timebase to 10ms/div, trigger on channel 1 rising edge at 2V, and capture 5 waveforms"*
  - *"Load the thermal analysis protocol, set target temperature to 75°C, enable automatic data logging, and start the heating sequence"*
- **Command Parsing and Mapping**: The language model decomposes natural language instructions into **structured MCP tool calls**, each mapped to specific **AutoHotkey macros** that interact with GUI elements (buttons, fields, menus).
- **Prerequisite Validation**: Before execution, the system verifies that all required GUI elements and laboratory capabilities are available and accessible through existing AHK profiles.
- **Sequential Execution**: Complex multi-step procedures are broken down into atomic operations, executed in proper sequence with state validation between steps.
- **Voice Integration Pathway**: The natural language interface naturally extends to **voice-controlled operation**, enabling hands-free laboratory interaction through speech-to-text integration.
- **Safety and Validation**: All commands undergo semantic validation to prevent unsafe operations, with confirmation prompts for destructive or high-risk actions.

### 6. Open-Source Ecosystem
- Outputs:  
  - MCP server + toolset for session control  
  - Bayesian agent with datasets and fault-injection harness  
  - Natural language command processor with safety validation  
  - Voice-to-MCP integration modules  
  - Edge profiles (Jetson/RPi)  
  - AHK profile library for common lab applications  
  - Documentation, benchmarks, and demo video  

---

## Implementation Plan

### Phase 1 – Planning (Months 1–3)
1. Define hidden states, observation features, and action sets.  
2. Collect GUI event logs from UNED labs (electronics, control, robotics).  
3. Extend Lab Gateway with MCP tool layer.  
4. Develop initial Bayesian model using collected data.  
5. **Design natural language command taxonomy** for common lab operations and map to GUI element interactions.
6. **Create AHK profile specifications** that expose laboratory GUI capabilities through standardized MCP tools.

### Phase 2 – Implementation (Months 4–6)
1. Deploy the agent on Jetson/Raspberry Pi hardware.  
2. Optimize performance with adaptive polling and CUDA kernels.  
3. **Implement natural language processor** with command parsing, validation, and MCP tool mapping.
4. **Develop voice integration modules** with speech-to-text and safety confirmation workflows.
5. Integrate closed-loop operation in real labs via Guacamole/RemoteApp.  
6. Conduct A/B testing against baseline scripted solutions, including **usability studies** for natural language vs. traditional GUI interaction.
7. Release open-source software, profiles, language models, and reproducible demo.  

---

## Expected Impact
- **Environmental:** Reduced wasted energy from failed sessions; extended hardware lifetime.  
- **Social:** Reliable access for students/researchers regardless of location or mobility; support for under-resourced institutions. **Natural language and voice interfaces** dramatically improve accessibility for users with disabilities and reduce the learning curve for complex laboratory software.
- **Scientific:** Bridges probabilistic AI methods with real GUI environments; creates reproducible benchmarks for Bayesian agents. **Language-driven automation** enables more intuitive experimental workflows and faster protocol development.
- **Educational:** **Conversational lab interaction** allows students to focus on experimental concepts rather than software complexity, improving learning outcomes and reducing technical barriers.
- **Market:** Enables sustainable operation of remote labs, lowering costs and unlocking new adoption opportunities across Europe. **Voice and natural language capabilities** differentiate the platform and expand addressable markets to include educational institutions seeking more accessible laboratory solutions.  

---

## Conclusion
This project introduces a novel **Bayesian edge agent** that pairs probabilistic reasoning with deterministic actuation to autonomously manage GUIs in remote laboratories, complemented by an **intuitive natural language interface** that democratizes laboratory access. By embedding both **resilience intelligence** and **conversational interaction** at the Lab Gateway, it ensures **robust, accessible, and scalable operation** while enabling voice-controlled experimentation.