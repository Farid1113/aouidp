use hmac::{Hmac, Mac};
use pyo3::prelude::*;
use sha2::Sha256;

type HmacSha256 = Hmac<Sha256>;

/// Accepts printable, non-whitespace ASCII codes (e.g. license keys), 6..=256 chars.
/// Rejects control characters, spaces and delimiters used to serialize CSV/JSON.
#[pyfunction]
pub fn validate_code(code: &str) -> bool {
    (6..=256).contains(&code.len())
        && code.bytes().all(|b| b.is_ascii_alphanumeric() || b"-_:./+".contains(&b))
}

/// Keyed fingerprint for deduplication. Plain SHA256 is unsuitable for low-entropy codes.
#[pyfunction]
pub fn fingerprint(code: &str, pepper: &str) -> PyResult<String> {
    if pepper.len() < 32 || !validate_code(code) {
        return Err(pyo3::exceptions::PyValueError::new_err("Invalid code or HMAC key"));
    }
    let mut mac = HmacSha256::new_from_slice(pepper.as_bytes())
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("Invalid HMAC key"))?;
    mac.update(code.as_bytes());
    Ok(hex::encode(mac.finalize().into_bytes()))
}

#[pyfunction]
pub fn masked_preview(code: &str) -> String {
    let count = code.chars().count();
    if count <= 4 { return "*".repeat(count); }
    format!("{}{}", "*".repeat(count - 4), code.chars().skip(count - 4).collect::<String>())
}

#[pymodule]
fn digital_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(validate_code, m)?)?;
    m.add_function(wrap_pyfunction!(fingerprint, m)?)?;
    m.add_function(wrap_pyfunction!(masked_preview, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validates_license_keys() {
        assert!(validate_code("ABCD-1234-ZYXW"));
        assert!(!validate_code("bad key with spaces"));
        assert!(!validate_code("short"));
        assert!(!validate_code("CTRL\nCHARS"));
    }
    #[test]
    fn fingerprints_are_deterministic_and_keyed() {
        let a = fingerprint("ABCD-1234", "0123456789abcdefghijklmnopqrstuvwxy").unwrap();
        let b = fingerprint("ABCD-1234", "0123456789abcdefghijklmnopqrstuvwxy").unwrap();
        let c = fingerprint("ABCD-1234", "another-0123456789abcdefghijklmnopq").unwrap();
        assert_eq!(a, b);
        assert_ne!(a, c);
        assert_eq!(a.len(), 64);
    }
    #[test]
    fn previews_do_not_expose_prefix() {
        assert_eq!(masked_preview("ABCD-1234"), "*****1234");
    }
}
