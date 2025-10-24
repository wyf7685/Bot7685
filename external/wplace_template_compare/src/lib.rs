mod color_map;
mod compare;

use pyo3::prelude::*;

#[pymodule]
#[pyo3(name="_compare")]
fn wplace_template_compare(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compare::compare, m)?)?;
    Ok(())
}
