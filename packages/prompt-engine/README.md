# Prompt Engine packages

This directory contains source-managed, public Prompt Workbench packages. A package may declare a procedural Skill, a workflow profile, and short generic knowledge documents.

The repository includes code and templates only. Private runtime knowledge belongs under the configured local runtime root and is loaded only through a bounded namespace; it must never be copied here. Do not add user prompts, conversation history, credentials, host details, model paths, empirical private results, or generated runtime artifacts to this directory.

The initial `comfyui-prompt-generator` Skill and `anima-base-v1` workflow are declarative foundations. They do not invoke a model, generate prompts, call ComfyUI, or perform QA.
