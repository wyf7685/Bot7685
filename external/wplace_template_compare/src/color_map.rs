use image::Rgba;
use lazy_static::lazy_static;

lazy_static! {
    static ref COLORS_MAP: std::collections::HashMap<&'static str, (u8, u8, u8)> = {
        let mut m = std::collections::HashMap::new();
        // m.insert("Transparent", (0, 0, 0));
        m.insert("Black", (0, 0, 0));
        m.insert("Dark Gray", (60, 60, 60));
        m.insert("Gray", (120, 120, 120));
        m.insert("Light Gray", (210, 210, 210));
        m.insert("White", (255, 255, 255));
        m.insert("Deep Red", (96, 0, 24));
        m.insert("Red", (237, 28, 36));
        m.insert("Orange", (255, 127, 39));
        m.insert("Gold", (246, 170, 9));
        m.insert("Yellow", (249, 221, 59));
        m.insert("Light Yellow", (255, 250, 188));
        m.insert("Dark Green", (14, 185, 104));
        m.insert("Green", (19, 230, 123));
        m.insert("Light Green", (135, 255, 94));
        m.insert("Dark Teal", (12, 129, 110));
        m.insert("Teal", (16, 174, 166));
        m.insert("Light Teal", (19, 225, 190));
        m.insert("Dark Blue", (40, 80, 158));
        m.insert("Blue", (64, 147, 228));
        m.insert("Cyan", (96, 247, 242));
        m.insert("Indigo", (107, 80, 246));
        m.insert("Light Indigo", (153, 177, 251));
        m.insert("Dark Purple", (120, 12, 153));
        m.insert("Purple", (170, 56, 185));
        m.insert("Light Purple", (224, 159, 249));
        m.insert("Dark Pink", (203, 0, 122));
        m.insert("Pink", (236, 31, 128));
        m.insert("Light Pink", (243, 141, 169));
        m.insert("Dark Brown", (104, 70, 52));
        m.insert("Brown", (149, 104, 42));
        m.insert("Beige", (248, 178, 119));
        m.insert("Medium Gray", (170, 170, 170));
        m.insert("Dark Red", (165, 14, 30));
        m.insert("Light Red", (250, 128, 114));
        m.insert("Dark Orange", (228, 92, 26));
        m.insert("Light Tan", (214, 181, 148));
        m.insert("Dark Goldenrod", (156, 132, 49));
        m.insert("Goldenrod", (197, 173, 49));
        m.insert("Light Goldenrod", (232, 212, 95));
        m.insert("Dark Olive", (74, 107, 58));
        m.insert("Olive", (90, 148, 74));
        m.insert("Light Olive", (132, 197, 115));
        m.insert("Dark Cyan", (15, 121, 159));
        m.insert("Light Cyan", (187, 250, 242));
        m.insert("Light Blue", (125, 199, 255));
        m.insert("Dark Indigo", (77, 49, 184));
        m.insert("Dark Slate Blue", (74, 66, 132));
        m.insert("Slate Blue", (122, 113, 196));
        m.insert("Light Slate Blue", (181, 174, 241));
        m.insert("Light Brown", (219, 164, 99));
        m.insert("Dark Beige", (209, 128, 81));
        m.insert("Light Beige", (255, 197, 165));
        m.insert("Dark Peach", (155, 82, 73));
        m.insert("Peach", (209, 128, 120));
        m.insert("Light Peach", (250, 182, 164));
        m.insert("Dark Tan", (123, 99, 82));
        m.insert("Tan", (156, 132, 107));
        m.insert("Dark Slate", (51, 57, 65));
        m.insert("Slate", (109, 117, 141));
        m.insert("Light Slate", (179, 185, 209));
        m.insert("Dark Stone", (109, 100, 63));
        m.insert("Stone", (148, 140, 107));
        m.insert("Light Stone", (205, 197, 158));
        m
    };
}

fn color_distance(c1: (u8, u8, u8), c2: (u8, u8, u8)) -> u32 {
    (c1.0 as i32 - c2.0 as i32).pow(2) as u32
        + (c1.1 as i32 - c2.1 as i32).pow(2) as u32
        + (c1.2 as i32 - c2.2 as i32).pow(2) as u32
}

pub(crate) fn find_color_name(pixel: &Rgba<u8>) -> &'static str {
    if pixel[3] == 0 {
        return "Transparent";
    }

    let rgb = (pixel[0], pixel[1], pixel[2]);
    for (name, &value) in COLORS_MAP.iter() {
        if value == rgb {
            return name;
        }
    }

    // not found, find the closest one
    let mut closest_name = "";
    let mut closest_distance = u32::MAX;
    for (name, &value) in COLORS_MAP.iter() {
        let dist = color_distance(rgb, value);
        if dist < closest_distance {
            closest_distance = dist;
            closest_name = name;
        }
    }
    closest_name
}
