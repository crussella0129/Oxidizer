// Expected: E0106 — missing lifetime specifier on a returned reference.

pub struct Parser {
    source: String,
}

pub fn first_word(text: &str, fallback: &str) -> &str {
    match text.split_whitespace().next() {
        Some(w) => w,
        None => fallback,
    }
}
