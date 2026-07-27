# Layer 2 — 03_api: what is the signature, which method

The user needs the std API surface: a signature, a trait bound, whether a method
exists, what it returns.

## Inputs

| What | Where from | Load when |
|---|---|---|
| One item or method | `oxidize api <path>` | Always the first move |
| Candidates, if the name is unknown | `oxidize search "<what it does>" --source std` | You do not know the name |
| Usage in context | `oxidize search "<type>" --source rust-by-example` | The signature alone is not enough |

## Process

1. `oxidize api std::vec::Vec::retain`. Bare and partial forms work too: `Vec`,
   `Vec::retain`, `HashMap::entry`. Resolution prefers concrete items over
   modules and verifies the member actually exists on the type.
2. If you do not know the method name, search by behaviour:
   `oxidize search "remove elements matching predicate" --source std`.
3. Read the signature carefully before answering. Rust API mistakes are almost
   always in the details — `&self` vs `&mut self` vs `self`, `Option<&T>` vs
   `&Option<T>`, whether it returns an iterator or a collection, what the trait
   bounds require.
4. Note stability. The mirror is pinned to the user's toolchain, so if it is not
   there, the user's compiler does not have it either.

## Budget

Never `api` a bare container type and read the whole thing — `Vec` is ~96k
tokens, `HashMap` similar. Always ask for the member:
`oxidize api Vec::retain`, not `oxidize api Vec` followed by scrolling. When you
genuinely need the type overview, the default budget gives you the summary and
the member list, which is usually enough to pick the method you actually wanted.

## Outputs

- The exact signature, in a `rust` code block.
- What it does, in one or two sentences.
- A usage example if the signature is not self-explanatory — especially for
  anything with closures or non-obvious trait bounds.
- The `doc.rust-lang.org` URL with the `#method.name` anchor.

## Hand off

- Their call does not compile → `01_diagnose`
- They are asking which of several approaches is better style → `06_idiom`
- The type involves raw pointers or `unsafe` → `05_unsafe`
