// Compiles, but is unsafe/FFI territory: the Nomicon governs the invariants
// this code must uphold. Used to check that Oxidizer routes to 05_unsafe
// rather than to the Book.

use std::ffi::c_void;

unsafe extern "C" {
    fn memcpy(dest: *mut c_void, src: *const c_void, n: usize) -> *mut c_void;
}

/// # Safety
/// `src` and `dst` must not overlap and both must be valid for `len` bytes.
pub unsafe fn raw_copy(dst: *mut u8, src: *const u8, len: usize) {
    unsafe {
        memcpy(dst as *mut c_void, src as *const c_void, len);
    }
}
