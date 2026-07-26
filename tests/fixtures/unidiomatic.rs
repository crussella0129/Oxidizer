// Compiles cleanly, but is full of clippy-flagged non-idioms.
// Used to check the idiom path: warnings, not errors.

pub fn sum_all(values: &Vec<i32>) -> i32 {
    let mut total = 0;
    for i in 0..values.len() {
        total += values[i];
    }
    return total;
}

pub fn describe(name: &String) -> String {
    if name.len() == 0 {
        return "empty".to_string();
    }
    format!("{}", name)
}
