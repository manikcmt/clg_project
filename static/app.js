document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) {
      event.preventDefault();
    }
  });
});

document.querySelectorAll("[data-reveal-phone]").forEach((button) => {
  button.addEventListener("click", async () => {
    const studentId = button.dataset.revealPhone;
    const output = document.querySelector(`[data-phone-output="${studentId}"]`);
    if (button.dataset.visible === "true") {
      output.textContent = "Hidden";
      button.textContent = "Show";
      button.dataset.visible = "false";
      return;
    }

    button.disabled = true;
    try {
      const response = await fetch(`/portal/students/${studentId}/phone`);
      if (!response.ok) {
        throw new Error("Could not load this phone number.");
      }
      const data = await response.json();
      output.textContent = data.phone_number;
      button.textContent = "Hide";
      button.dataset.visible = "true";
    } catch {
      output.textContent = "Unavailable";
    } finally {
      button.disabled = false;
    }
  });
});

const selectAllStudents = document.querySelector("[data-select-all-students]");
if (selectAllStudents) {
  const studentSelections = document.querySelectorAll("[data-student-select]");
  selectAllStudents.addEventListener("change", () => {
    studentSelections.forEach((checkbox) => {
      checkbox.checked = selectAllStudents.checked;
    });
  });
  studentSelections.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      selectAllStudents.checked = Array.from(studentSelections).every(
        (studentSelection) => studentSelection.checked,
      );
    });
  });
}

[
  ["[data-select-all-teachers]", "[data-teacher-select]"],
  ["[data-select-all-semester-requests]", "[data-semester-request-select]"],
].forEach(([selectAllSelector, selectionSelector]) => {
  const selectAll = document.querySelector(selectAllSelector);
  if (!selectAll) {
    return;
  }
  const selections = document.querySelectorAll(selectionSelector);
  selectAll.addEventListener("change", () => {
    selections.forEach((selection) => {
      selection.checked = selectAll.checked;
    });
  });
  selections.forEach((selection) => {
    selection.addEventListener("change", () => {
      selectAll.checked =
        selections.length > 0 &&
        Array.from(selections).every((item) => item.checked);
    });
  });
});

const selectAllEnrollments = document.querySelector("[data-select-all-enrollments]");
if (selectAllEnrollments) {
  const enrollmentSelections = document.querySelectorAll("[data-enrollment-select]");
  selectAllEnrollments.addEventListener("change", () => {
    enrollmentSelections.forEach((selection) => {
      selection.checked = selectAllEnrollments.checked;
    });
  });
  enrollmentSelections.forEach((selection) => {
    selection.addEventListener("change", () => {
      selectAllEnrollments.checked =
        enrollmentSelections.length > 0 &&
        Array.from(enrollmentSelections).every((item) => item.checked);
    });
  });
}

const dashboardThemes = ["glass", "light", "blue", "dark"];
const themeChoices = document.querySelectorAll("[data-theme-choice]");
if (themeChoices.length) {
  const savedTheme = localStorage.getItem("dashboard-theme");
  const initialTheme = dashboardThemes.includes(savedTheme) ? savedTheme : "glass";

  const setDashboardTheme = (theme) => {
    document.body.dataset.theme = theme;
    localStorage.setItem("dashboard-theme", theme);
    themeChoices.forEach((choice) => {
      choice.setAttribute("aria-pressed", String(choice.dataset.themeChoice === theme));
    });
  };

  setDashboardTheme(initialTheme);
  themeChoices.forEach((choice) => {
    choice.addEventListener("click", () => {
      setDashboardTheme(choice.dataset.themeChoice);
    });
  });
}
