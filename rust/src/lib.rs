use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};

struct Matrix {
    width: i32,
    height: i32,
    data: Vec<i32>,
}

impl Matrix {
    fn new(width: i32, height: i32) -> Matrix {
        Matrix {
            width,
            height,
            data: vec![0; width as usize * height as usize],
        }
    }
    fn get(&self, x: i32, y: i32) -> i32 {
        assert!(x < self.width);
        assert!(y < self.height);
        self.data[((self.width * (y + 1)) + (x + 1)) as usize]
    }

    fn set(&mut self, x: i32, y: i32, value: i32) {
        assert!(x < self.width);
        assert!(y < self.height);
        self.data[((self.width * (y + 1)) + (x + 1)) as usize] = value;
    }
}

#[pyfunction]
/// Derived from Wikipedia, the best possible source for an algorithm:
/// https://en.wikipedia.org/w/index.php?title=Damerau%E2%80%93Levenshtein_distance&oldid=1050388400#Distance_with_adjacent_transpositions
pub fn damerau_levenshtein_distance(a: &str, b: &str) -> i32 {
    // Strings are 1-indexed, and d is -1-indexed.
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();

    let a_len: i32 = a.len().try_into().unwrap();
    let b_len: i32 = b.len().try_into().unwrap();

    let chars_set: HashSet<&char> = HashSet::from_iter(a_chars.iter().chain(b_chars.iter()));
    let mut da: HashMap<char, i32> = HashMap::from_iter(chars_set.iter().map(|&&ch| (ch, 0)));

    let mut matrix = Matrix::new(a_len + 2, b_len + 2);

    let maxdist = a_len + b_len;
    matrix.set(-1, -1, maxdist);

    for i in 0..(a_len + 1) {
        matrix.set(i, -1, maxdist);
        matrix.set(i, 0, i);
    }

    for j in 0..(b_len + 1) {
        matrix.set(-1, j, maxdist);
        matrix.set(0, j, j);
    }

    for i in 1..(a_len + 1) {
        let mut db = 0;
        for j in 1..(b_len + 1) {
            let k = da[&b_chars[j as usize - 1]];
            let l = db;
            let cost = if a_chars[i as usize - 1] == b_chars[j as usize - 1] {
                db = j;
                0
            } else {
                1
            };
            matrix.set(
                i,
                j,
                *vec![
                    matrix.get(i - 1, j - 1) + cost, // substitution
                    matrix.get(i, j - 1) + 1,        // insertion
                    matrix.get(i - 1, j) + 1,        // deletion
                    matrix.get(k - 1, l - 1) + (i - k - 1) + 1 + (j - l - 1),
                ]
                .iter()
                .min()
                .unwrap_or(&0), // transposition
            );
        }
        da.insert(a_chars[i as usize - 1], i);
    }

    matrix.get(a_len, b_len)
}

/// A Python module implemented in Rust.
#[pymodule]
fn snooty_oxide(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(damerau_levenshtein_distance, m)?)?;
    Ok(())
}
