rd /S /Q dist
python setup.py sdist bdist_wheel
python -m twine upload dist/*
pause