# Oxidizer
(***Under Construction***) An agent-agnostic Rust lang skill, with instructions for live updates from Rust Lang official canon sources.

***Sprint 0 Intitialization Prompt***: 

- **Project Format**: An instruction set to clone and establish mirrors of the various Rust canon materials (included below) + create an agentic file structure based on the paper "Interpretable Context Methodology: Folder Structure as Agent Architecture" (https://arxiv.org/html/2603.16021v1) to handle when to access pertinent information situationally, so as to not saturate the agent model's context window with the large amount of data being handled here. You will then deploy that via MCP over stdio using the standard Rust MCP SDK.

- **Live Sources to Pull and build MCP from**:
  - Rust-lang Official Documentation: https://doc.rust-lang.org , most notably:
    - The Book: [https://doc.rust-lang.org/book/]
      - Brown Univ. Fork : [https://rust-book.cs.brown.edu/]     
    - Rust By Example: [https://doc.rust-lang.org/rust-by-example/]
    - Crate Std (Rust Standard Library Documentation): [https://doc.rust-lang.org/std/index.html]
    - The Rust Reference: [https://doc.rust-lang.org/reference/index.html]
    - The Rustonomicon: [https://doc.rust-lang.org/nomicon/]
  - Crate Categories: [https://lib.rs/#home-categories]
  - Brown Univ. C++ to Rust Phrasebook: [https://cel.cs.brown.edu/crp/]
