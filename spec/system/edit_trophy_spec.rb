require "rails_helper"

describe "editing a trophy" do
  it "succeeds with required fields after logging in via email" do
    worts_member = create(:user)
    create(:trophy, bjcp_score: 35, user: worts_member)

    login_as(worts_member)

    click_link "Trophies"
    click_link "Edit Trophy"

    fill_in :trophy_bjcp_score, with: 33
    click_on "Update Trophy"

    expect(page).to have_content("Trophy successfully updated")
    expect(page).to have_content(33)
  end
end
