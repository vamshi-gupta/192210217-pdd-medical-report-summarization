<?php
$servername = "localhost";
$username = "root";
$password = "";
$dbname = "hospital_db";

// Create connection
$conn = new mysqli($servername, $username, $password, $dbname);

// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    // Check for required fields
    if (!empty($_POST['patient_name']) && !empty($_POST['doctor_name']) && !empty($_POST['hospital_name']) && !empty($_POST['last_visited_date']) && !empty($_POST['date']) && !empty($_FILES['file'])) {
        
        $patient_name = $conn->real_escape_string($_POST['patient_name']);
        $doctor_name = $conn->real_escape_string($_POST['doctor_name']);
        $hospital_name = $conn->real_escape_string($_POST['hospital_name']);
        $last_visited_date = $conn->real_escape_string($_POST['last_visited_date']);
        $date = $conn->real_escape_string($_POST['date']);

        // Validate date format (YYYY-MM-DD)
        if (!preg_match("/^\d{4}-\d{2}-\d{2}$/", $last_visited_date) || !preg_match("/^\d{4}-\d{2}-\d{2}$/", $date)) {
            echo json_encode(["message" => "Invalid date format. Use YYYY-MM-DD."]);
            exit;
        }

        // Handle file upload
        $target_dir = "uploads/";
        if (!is_dir($target_dir)) {
            mkdir($target_dir, 0777, true); // Ensure uploads directory exists
        }
        
        $file_name = basename($_FILES["file"]["name"]);
        $target_file = $target_dir . time() . "_" . $file_name; // Unique file name
        $file_type = strtolower(pathinfo($target_file, PATHINFO_EXTENSION));

        if ($file_type != "pdf") {
            echo json_encode(["message" => "Only PDF files are allowed."]);
            exit;
        }

        if (move_uploaded_file($_FILES["file"]["tmp_name"], $target_file)) {
            // Insert data into the database
            $sql = "INSERT INTO discharge_reports (patient_name, doctor_name, hospital_name, last_visited_date, date, file_path) 
                    VALUES ('$patient_name', '$doctor_name', '$hospital_name', '$last_visited_date', '$date', '$target_file')";
            
            if ($conn->query($sql)) {
                echo json_encode(["message" => "Record added successfully.", "file_path" => $target_file]);
            } else {
                echo json_encode(["message" => "Database Error: " . $conn->error]);
            }
        } else {
            echo json_encode(["message" => "Error uploading file."]);
        }
    } else {
        echo json_encode(["message" => "Invalid input or missing required fields."]);
    }
}

$conn->close();
?>
