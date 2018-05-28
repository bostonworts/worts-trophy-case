require 'rails_helper'

RSpec.describe Trophy, type: :model do
  it "is valid if all required fields are filled out and valid" do
    trophy = Trophy.new(
      bjcp_score: 25,
      competition_date: Date.yesterday,
      competition_url: "http://bhc.wort.org",
      subcategory: Subcategory.last,
      user: create(:user)
    )

    expect(trophy).to be_valid
  end

  it "is valid if all required and optional fields are filled out and valid" do
    trophy = Trophy.new(
      bjcp_score: 25,
      competition_date: Date.yesterday,
      competition_url: "http://bhc.wort.org",
      place: 1,
      place_context: "category",
      subcategory: Subcategory.last,
      recipe_url: "http://iancanderson.com/brewlog/batches/001",
      user: create(:user)
    )

    expect(trophy).to be_valid
  end
end
