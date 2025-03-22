<?php
session_start();
include('db.php');

if (!isset($_SESSION['user_id'])) {
    die("User not logged in");
}

if (isset($_GET['id'])) {
    $summary_id = intval($_GET['id']);
    $user_id = $_SESSION['user_id'];

    $stmt = $conn->prepare("SELECT patient_name, doctor_name, date, summary FROM summaries WHERE id = ? AND user_id = ?");
    $stmt->bind_param("ii", $summary_id, $user_id);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($row = $result->fetch_assoc()) {
        $filename = "summary_" . $row['patient_name'] . "_" . $row['date'] . ".txt";
        header("Content-Disposition: attachment; filename=\"$filename\"");
        header("Content-Type: text/plain");
        
        echo "Summary for " . $row['patient_name'] . "\n";
        echo "Doctor: " . $row['doctor_name'] . "\n";
        echo "Date: " . $row['date'] . "\n\n";
        echo "Summary:\n" . $row['summary'];
    } else {
        die("Summary not found");
    }
    $stmt->close();
}
?>
