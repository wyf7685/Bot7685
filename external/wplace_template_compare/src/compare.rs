use crate::color_map::find_color_name;
use image::{GenericImageView, Pixel};
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyInt, PyList, PyString, PyTuple};
use std::collections::HashMap;

struct ColorEntry {
    name: &'static str,
    count: usize,
    total: usize,
    pixels: Vec<(usize, usize)>,
}

impl ColorEntry {
    fn new(name: &'static str) -> Self {
        ColorEntry {
            name,
            count: 0,
            total: 0,
            pixels: Vec::new(),
        }
    }

    fn to_pytuple(&self, py: Python) -> PyResult<Py<PyTuple>> {
        let elements: Vec<Py<PyAny>> = vec![
            PyString::new(py, &self.name).into(),
            PyInt::new(py, self.count).into(),
            PyInt::new(py, self.total).into(),
            PyList::new(py, &self.pixels)?.into(),
        ];
        let tuple = PyTuple::new(py, elements)?;
        Ok(tuple.into())
    }
}

fn load_image(image_bytes: &Bound<'_, PyBytes>) -> PyResult<image::DynamicImage> {
    match image::load_from_memory(image_bytes.as_bytes()) {
        Ok(img) => Ok(img),
        Err(e) => {
            let msg = format!("Failed to load image: {}", e);
            Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(msg))
        }
    }
}

#[pyfunction]
#[pyo3(signature = (template_bytes, actual_bytes, include_pixels))]
pub(crate) fn compare(
    py: Python,
    template_bytes: &Bound<'_, PyBytes>,
    actual_bytes: &Bound<'_, PyBytes>,
    include_pixels: bool,
) -> PyResult<Py<PyAny>> {
    // 从字节流加载图像
    let template_img = load_image(template_bytes)?;
    let actual_img = load_image(actual_bytes)?;

    let compare_func = move || -> PyResult<Py<PyList>> {
        // 转换为 RGBA 格式
        let template_rgba = template_img.to_rgba8();
        let actual_rgba = actual_img.to_rgba8();

        // 获取图像尺寸
        let (width, height) = template_img.dimensions();

        // 创建 diff_pixels 字典
        let mut diff_pixels: HashMap<&'static str, ColorEntry> = HashMap::new();

        // 遍历每个像素
        for y in 0..height {
            for x in 0..width {
                let template_pixel = template_rgba.get_pixel(x, y);

                // 跳过模板中的透明像素
                if template_pixel[3] == 0 {
                    continue;
                }

                // 获取颜色名称
                let color_name = find_color_name(template_pixel);

                // 获取或创建 ColorEntry
                let entry = diff_pixels
                    .entry(color_name)
                    .or_insert_with(|| ColorEntry::new(color_name));

                // 统计模板像素总数
                entry.total += 1;

                // 如果模板像素颜色与实际像素颜色不同
                if template_pixel.to_rgb() != actual_rgba.get_pixel(x, y).to_rgb()
                // 或者实际像素是透明的
                    || actual_rgba.get_pixel(x, y)[3] == 0
                {
                    entry.count += 1;
                    if include_pixels {
                        entry.pixels.push((x as usize, y as usize));
                    }
                }
            }
        }

        let mut diff_values: Vec<ColorEntry> = diff_pixels.into_values().collect();
        diff_values.sort_by(|a, b| b.total.cmp(&a.total).then_with(|| a.name.cmp(&b.name)));

        let result = Python::attach(|py| -> PyResult<Py<PyList>> {
            let result = PyList::empty(py);
            for entry in diff_values {
                result.append(entry.to_pytuple(py)?)?;
            }
            Ok(result.into())
        })?;

        Ok(result)
    };

    let event_loop = py.import("asyncio")?.call_method0("get_event_loop")?;
    let fut = event_loop.call_method0("create_future")?;
    let call_soon_threadsafe = event_loop.getattr("call_soon_threadsafe")?.unbind();
    let set_result = fut.getattr("set_result")?.unbind();
    let set_exception = fut.getattr("set_exception")?.unbind();

    std::thread::spawn(move || {
        Python::attach(|py| match compare_func() {
            Ok(result) => {
                call_soon_threadsafe
                    .call(py, (set_result, result), None)
                    .unwrap();
            }
            Err(err) => {
                call_soon_threadsafe
                    .call(py, (set_exception, err), None)
                    .unwrap();
            }
        });
    });

    Ok(fut.into())
}
