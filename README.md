# Oxidizer
An agent-agnostic Rust lang skill, with instructions for live updates from Rust Lang official canon sources.

***Sprint 0 Intitialization Prompt***: 

- Project Format: An instruction set to clone the various Rust canon materials (included below) and deploy them via an MCP server, perhaps serving it locally via MCP over stdio using the standard Rust MCP SDK + create an agentic file structure based on the paper "Interpretable Context Methodology: Folder Structure as Agent Architecture" (https://arxiv.org/html/2603.16021v1) to handle when to access pertinent information situationally, so as to not saturate the agent model's context window with the large amount of data being handled here. 

- Live Sources to Pull and build MCP from:
  - Rust-lang Official Documentation: https://doc.rust-lang.org , most notably:
    - The Book: [https://doc.rust-lang.org/book/]
      - Notable Book Forks: 
        - Brown Univ. Fork : [https://rust-book.cs.brown.edu/]  
    - Rust By Example: [https://doc.rust-lang.org/rust-by-example/]
    - Crate Std (Rust Standard Library Documentation): [https://doc.rust-lang.org/std/index.html]
    - The Rustonomicon: [https://doc.rust-lang.org/nomicon/]
  - Crate Categories: https://lib.rs/#home-categories
  
- The ICM Realignment: Layered Folders
  - The heart of the ICM paper (arXiv:2603.16021) is replacing complex framework-level agent code with a predictable, filesystem-centric hierarchy. It relies on Layered Context Loading and "One Stage, One Job".
  - Instead of letting the agent arbitrarily search the entire Rust canon, organize the Oxidizer Workspace into five strict, isolated layers:
    - oxidizer-workspace/
      │
      ├── 00_identity/              # LAYER 0: System instructions & persona
      │   └── CLAUDE.md             # Defines "Oxidizer" and its capabilities
      │
      ├── 01_routing/               # LAYER 1: The Master Catalog
      │   └── CONTEXT.md            # Mapping file telling the agent where to look
      │
      ├── 02_stages/                # LAYER 2: Stage Contracts (One job per stage)
      │   ├── 01_search_intent/     # Decides if the problem is Syn, Std-Lib, or Async
      │   ├── 02_context_fetch/     # Gathers the precise markdown chunks
      │   └── 03_generation/        # Compiles the final answer
      │
      ├── 03_reference/             # LAYER 3: The Cloned Canon Material (Markdown only)
      │   ├── the-book/
      │   ├── brown-fork/
      │   ├── rust-by-example/
      │   ├── nomicon/
      │   └── other_docs.../              # Extracted plain-text/markdown of original documents
      │
      └── 04_artifacts/             # LAYER 4: Output and State
          └── working_code.rs       # The actual scratchpad where code is edited
