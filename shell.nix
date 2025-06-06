{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  # List of packages to be available in the shell.
  packages = with pkgs; [
    # Add chromedriver directly. Nix will place it on the PATH.
    chromedriver
    # You may also need google-chrome-stable for a headless browser
    chromium

    # The Python environment with its packages
    (python311.withPackages (ps: with ps; [
      # Core FastAPI components
      fastapi
      uvicorn
      python-multipart

      # Selenium components
      selenium
      # webdriver-manager has been REMOVED.

      # Other dependencies
      nest-asyncio
    ]))
  ];

  shellHook = ''
    echo "Nix shell for FastAPI & Selenium activated!"
    echo "ChromeDriver is available on your PATH."
    # The PYTHONPATH is automatically managed by python.withPackages,
    # so manual export is not usually necessary.
  '';
}