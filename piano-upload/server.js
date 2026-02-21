const express = require('express');
const multer = require('multer');
const app = express();
const fs = require('fs');
const path = require('path');

// Configuration de Multer pour le stockage des fichiers
const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        // Déterminer le dossier basé sur le nom de fichier ou un paramètre (ex. : req.body.note)
        const note = req.body.note; // Assurez-vous que le formulaire envoie cette information.
        const dir = `uploads/${note}`;

        // Créer le dossier s'il n'existe pas
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }

        cb(null, dir);
    },
    filename: function (req, file, cb) {
        const note = req.body.note;
        const originalName = file.originalname;
        const fileExt = path.extname(originalName);
        const baseName = path.basename(originalName, fileExt);

        let newName = originalName;
        let counter = 1;

        // Vérifiez si le fichier existe déjà et modifiez le nom si nécessaire
        const dirPath = path.join(__dirname, 'uploads', note);
        while (fs.existsSync(path.join(dirPath, newName))) {
            newName = `${baseName}(${counter})${fileExt}`; // Ajoute un compteur entre parenthèses
            counter++;
        }

        cb(null, newName); // Conserve ou modifie le nom d'origine de façon unique
    }
});

const upload = multer({
    storage: storage, fileFilter: (req, file, cb) => {
        const ext = path.extname(file.originalname).toLowerCase();
        if (ext !== '.wav' && ext !== '.mp3') {
            return cb(new Error('Only .wav and .mp3 files are allowed.'));
        }
        cb(null, true);
    }
});

// Middleware pour servir des fichiers statiques
app.use(express.static('public'));

// Route pour le téléchargement de fichiers
app.post('/upload', upload.single('file'), (req, res) => {
    if (req.file) {
        res.send('Fichier téléchargé avec succès : ' + req.file.filename);
    } else {
        res.status(400).send('Erreur pendant le chargement du fichier.');
    }
});

// Route pour l'interface utilisateur
app.get('/', (req, res) => {
    res.sendFile(__dirname + '/public/index.html');
});

// Route to list files for a specific note
app.get('/files/:note', (req, res) => {
    const note = req.params.note;

    // Path traversal protection
    if (note.includes('..') || note.includes('/') || note.includes('\\')) {
        return res.status(400).json({ error: 'Invalid note parameter' });
    }

    const dirPath = path.join(__dirname, 'uploads', note);

    // Return empty array if directory doesn't exist
    if (!fs.existsSync(dirPath)) {
        return res.json([]);
    }

    fs.readdir(dirPath, (err, files) => {
        if (err) {
            return res.status(500).json({ error: 'Error reading files.' });
        }

        // Filter .wav and .mp3 files
        const audioFiles = files.filter(file => {
            const ext = path.extname(file).toLowerCase();
            return ext === '.wav' || ext === '.mp3';
        });

        res.json(audioFiles);
    });
});

// Route to delete a specific file
app.delete('/delete/:note/:filename', (req, res) => {
    const { note, filename } = req.params;

    // Path traversal protection
    if (note.includes('..') || note.includes('/') || note.includes('\\') ||
        filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
        return res.status(400).json({ error: 'Invalid parameters' });
    }

    const filePath = path.join(__dirname, 'uploads', note, filename);

    fs.unlink(filePath, (err) => {
        if (err) {
            return res.status(500).json({ message: 'Error deleting file.' });
        }
        res.json({ message: 'File deleted successfully.' });
    });
});

// Démarrer le serveur
const PORT = 80;
const HOST = '0.0.0.0';
app.listen(PORT, HOST, () => {
    console.log(`Serveur démarré sur http://${HOST}:${PORT}`);
});

