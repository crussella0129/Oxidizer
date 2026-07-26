// Expected: E0502 — mutable borrow while an immutable borrow is live.
// The classic "push while holding a reference into the vec" mistake.

pub fn longest_then_grow(words: &mut Vec<String>) -> usize {
    let first = &words[0];
    words.push(String::from("appended"));
    first.len()
}
