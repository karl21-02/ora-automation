// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::path::Path;
use walkdir::WalkDir;

#[derive(Debug, Serialize)]
struct GitRepo {
    name: String,
    path: String,
    language: Option<String>,
}

/// Scan a directory for git repositories (folders containing .git)
#[tauri::command]
fn scan_git_repos(folder_path: String, max_depth: Option<usize>) -> Result<Vec<GitRepo>, String> {
    // 경로 유효성 검사
    let path = Path::new(&folder_path);
    if !path.exists() {
        return Err("Folder does not exist".to_string());
    }
    if !path.is_dir() {
        return Err("Path is not a directory".to_string());
    }

    let depth = max_depth.unwrap_or(3);
    let mut repos = Vec::new();

    for entry in WalkDir::new(path)
        .max_depth(depth)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let entry_path = entry.path();
        if entry_path.is_dir() && entry_path.file_name().map_or(false, |n| n == ".git") {
            if let Some(parent) = entry_path.parent() {
                let name = parent
                    .file_name()
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_else(|| "unknown".to_string());

                let language = detect_language(parent);

                repos.push(GitRepo {
                    name,
                    path: parent.to_string_lossy().to_string(),
                    language,
                });
            }
        }
    }

    Ok(repos)
}

/// Simple language detection based on files present
fn detect_language(repo_path: &Path) -> Option<String> {
    let indicators = [
        ("Cargo.toml", "Rust"),
        ("package.json", "JavaScript"),
        ("pyproject.toml", "Python"),
        ("requirements.txt", "Python"),
        ("go.mod", "Go"),
        ("pom.xml", "Java"),
        ("build.gradle", "Java"),
        ("Gemfile", "Ruby"),
        ("mix.exs", "Elixir"),
        ("pubspec.yaml", "Dart"),
    ];

    for (file, lang) in indicators {
        if repo_path.join(file).exists() {
            return Some(lang.to_string());
        }
    }

    None
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![scan_git_repos])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
