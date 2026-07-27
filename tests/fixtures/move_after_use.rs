// Expected: E0382 — use of a value after it has been moved.

pub fn consume(v: Vec<i32>) -> usize {
    v.len()
}

pub fn run() -> usize {
    let numbers = vec![1, 2, 3];
    let total = consume(numbers);
    total + numbers.len()
}
